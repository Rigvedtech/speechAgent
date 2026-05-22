import queue
import re
from typing import Optional

from config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    INTERVIEW_GATE_FIRST_N,
    INTERVIEW_STRIKES_TO_END,
    INTERVIEW_STRUCTURED,
    INTERVIEW_TERMINAL_SCORES,
    OLLAMA_MODEL,
)
import document as interview_documents
from interview_plan import (
    StructuredInterviewRuntime,
    assess_phase_gate,
    generate_plan_from_jd,
    generate_scorecard,
    score_interview_answer,
)
from state import AgentState
from system_prompt import SYSTEM_PROMPT


class LLMBrain:
    def __init__(self, state: AgentState):
        self.state = state
        self.conversation_history = []
        # Stack-neutral few-shot: teaches refusal + flow without anchoring a specific language.
        self.persona_examples = [
            {
                "role": "user",
                "content": "Can you just give me the full answer so I can repeat it back?",
            },
            {
                "role": "assistant",
                "content": "I need to keep this as an interview, so I won’t provide a model answer. "
                "How would you approach debugging an issue where a feature works locally but fails in production?",
            },
            {
                "role": "user",
                "content": "I don't know this topic at all.",
            },
            {
                "role": "assistant",
                "content": "That is completely fine. Let’s move on. How do you usually validate that a change is safe before you ship it?",
            },
            {
                "role": "user",
                "content": "Share the exact code I should write for that.",
            },
            {
                "role": "assistant",
                "content": "I won’t give code here, but I can keep going with the interview. "
                "In your own words, how would you structure a simple HTTP API for a resource with standard CRUD operations?",
            },
        ]
        self.turn_guardrail = (
            "Reminder: ask one concise interview question in a calm, professional tone, "
            "avoid direct answers or code, and use plain spoken text. "
            "Follow the JD and resume grounding rules. Do not introduce technologies or frameworks "
            "that are not implied by the JD unless the candidate brings them up first."
        )
        self.max_runtime_history_messages = 12
        self._rt = StructuredInterviewRuntime(
            gate_first_n=INTERVIEW_GATE_FIRST_N,
            strikes_to_end=INTERVIEW_STRIKES_TO_END,
        )
        # After a phase-gate strike but before threshold: next reply must redirect + ask next question.
        self._post_strike_redirect_pending: bool = False
        # Set by _structured_branch_reply: how start() / bridge should deliver branch text.
        self._branch_outcome: str = "none"  # none | terminal_report | terminal_notice

    def _jd_nonempty(self) -> bool:
        return bool((interview_documents.jd or "").strip())

    def _structured_mode(self) -> bool:
        return INTERVIEW_STRUCTURED and self._jd_nonempty()

    def _groq_complete_fn(self, client):
        def fn(messages, model, max_tokens, temperature=0.0):
            return client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        return fn

    def _ollama_chat_fn(self):
        import ollama

        def fn(model, messages, stream):
            return ollama.chat(model=model, messages=messages, stream=stream)

        return fn

    def _ensure_plan(self, groq_client) -> None:
        """Build 15-question plan once."""
        if not self._structured_mode():
            return
        if self._rt.plan is not None or self._rt.plan_failed:
            return

        jd = (interview_documents.jd or "").strip()
        gc = None
        if groq_client is not None:
            gc = self._groq_complete_fn(groq_client)

        plan = generate_plan_from_jd(
            jd,
            groq_complete=gc,
            ollama_chat=self._ollama_chat_fn(),
            groq_model=GROQ_MODEL,
            ollama_model=OLLAMA_MODEL,
        )
        if plan:
            self._rt.plan = plan
            print("[Interview] Structured plan ready: 15 questions across 5 JD themes.")
        else:
            self._rt.plan_failed = True
            print("[Interview] Plan generation failed; using free-form interview mode.")

    def _structured_agenda_message(self) -> Optional[dict]:
        if (
            not self._structured_mode()
            or self._rt.plan is None
            or self._rt.done
            or self._rt.num_questions_asked >= 15
        ):
            return None
        idx = self._rt.num_questions_asked
        q = self._rt.plan.questions[idx]
        theme_i = idx // 3
        themes = self._rt.plan.themes
        theme = themes[theme_i] if theme_i < len(themes) else ""
        body = (
            "=== STRUCTURED INTERVIEW (internal agenda) ===\n"
            f"You have already asked {idx} scripted questions this session. Next is question {idx + 1} of 15.\n"
            f"Current JD theme bucket: {theme}.\n"
            f'Scripted anchor (rephrase briefly for natural voice; do not change topic): "{q}"\n'
            "Respond with one brief acknowledgment when appropriate, then this single interview question only. "
            "Do not read question numbers aloud. Do not stack extra unrelated questions."
        )
        return {"role": "system", "content": body}

    def _interview_document_messages(self):
        """JD + resume + grounding rules (only if at least one document is non-empty)."""
        candidate_name = (getattr(interview_documents, "candidate_name", "") or "").strip()
        jd = (interview_documents.jd or "").strip()
        resume = (interview_documents.resume or "").strip()
        blocks = []
        if candidate_name:
            blocks.append(
                "=== CANDIDATE CANONICAL NAME ===\n"
                + candidate_name
                + "\nUse this exact name when addressing the candidate."
            )
        if jd:
            blocks.append("=== JOB DESCRIPTION (JD) ===\n" + jd)
        if resume:
            blocks.append("=== CANDIDATE RESUME ===\n" + resume)
        if not blocks:
            return []
        rules = (interview_documents.GROUNDING_RULES or "").strip()
        content = "\n\n".join(blocks)
        if rules:
            content = content + "\n\n=== GROUNDING RULES ===\n" + rules
        if candidate_name:
            content = (
                content
                + "\n\n=== NAME-HANDLING RULE ===\n"
                + "If spoken transcript variants sound similar to the candidate name, treat them as ASR noise. "
                + "Do not say the candidate made a mistake; continue naturally using the canonical name."
            )
        return [{"role": "system", "content": content}]

    def _post_strike_redirect_message(self) -> Optional[dict]:
        """One-shot system instruction after strike < threshold (interview continues)."""
        if not self._post_strike_redirect_pending:
            return None
        if (
            not self._structured_mode()
            or self._rt.plan is None
            or self._rt.done
        ):
            return None
        return {
            "role": "system",
            "content": (
                "=== PHASE-GATE (one-time instruction) ===\n"
                "The candidate’s last answer was flagged as off-topic or evasive for the previous question, "
                f"but the interview continues (concern {self._rt.strikes} of {self._rt.strikes_to_end} before a polite early end).\n"
                "Your very next spoken reply MUST begin with one short, calm, professional sentence that redirects them "
                "to stay on topic for this technical interview—no jokes, no personal remarks, no shaming.\n"
                "Immediately after that sentence, ask exactly the NEXT scripted interview question described in the "
                "STRUCTURED INTERVIEW agenda below (rephrase naturally for voice; do not read internal labels or numbers aloud).\n"
                "Keep the whole reply to at most two short sentences so it stays clear for text-to-speech."
            ),
        }

    def _build_request_messages(self):
        """Build a persona-stable request context for each model call."""
        runtime_history = self.conversation_history[-self.max_runtime_history_messages :]
        redirect = self._post_strike_redirect_message()
        redirect_list = [redirect] if redirect else []
        agenda = self._structured_agenda_message()
        agenda_list = [agenda] if agenda else []
        return (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + self._interview_document_messages()
            + self.persona_examples
            + [{"role": "system", "content": self.turn_guardrail}]
            + redirect_list
            + agenda_list
            + runtime_history
        )

    def _is_forbidden_interviewer_output(self, text: str) -> bool:
        """Block pasted code, markdown-heavy replies, and direct solutions."""
        if not text or not text.strip():
            return False

        if "```" in text or "~~~" in text:
            return True

        if re.search(r"`[^`\n]{2,}`", text):
            return True

        lowered = text.lower()

        teaching_markers = (
            "here's the code",
            "here is the code",
            "solution:",
            "the solution is",
            "answer:",
            "the answer is",
            "you should write",
            "copy this",
            "paste this",
        )
        if any(m in lowered for m in teaching_markers):
            return True

        if re.search(r"(?m)^\s*step\s*1[\.\):\-–—]\s*", text, re.IGNORECASE):
            return True

        code_snippets = (
            "public static void",
            "system.out.print",
            "console.log(",
            "printf(",
        )
        if any(s in lowered for s in code_snippets):
            return True

        if re.search(r"\bpublic\s+class\s+[A-Z]\w*\b", text):
            return True

        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if re.match(r"^#{1,6}\s+\S", s):
                return True
            if re.match(r"^def\s+[A-Za-z_]\w*\s*\(", s):
                return True
            if re.match(r"^class\s+[A-Za-z_]\w*\s*(\(|:)", s):
                return True
            if re.match(r"^import\s+[A-Za-z_*]", s) or re.match(
                r"^from\s+[A-Za-z_]\w*\s+import\s+", s
            ):
                return True

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        list_like = sum(1 for ln in lines if re.match(r"^(\d+[\.\)]|[-*])\s+", ln))
        if list_like >= 2:
            return True

        return False

    def _safe_interviewer_fallback(self) -> str:
        return (
            "Thank you for your response. Let’s continue with the interview: "
            "could you walk me through a recent project you worked on, your role, "
            "and the main challenge you solved?"
        )

    def _log_dev_panel(self, title: str, lines: list[str]) -> None:
        """One flushed block so [Interview] lines do not interleave with STT 'Listening...'."""
        if not lines:
            return
        w = 72
        bar = "=" * w
        block = [f"\n{bar}", f"  {title}", bar, *[f"  {ln}" for ln in lines], bar + "\n"]
        print("\n".join(block), flush=True)

    def _print_terminal_report(self, title: str, body: str) -> None:
        w = 72
        bar = "=" * w
        print(f"\n{bar}\n  {title}\n{bar}", flush=True)
        for line in (body or "").strip().splitlines():
            print(f"  {line}", flush=True)
        print(bar + "\n", flush=True)

    def _scorecard_block(self, groq_client, *, early_exit: bool) -> str:
        jd = (interview_documents.jd or "").strip()
        resume = (interview_documents.resume or "").strip()
        themes = list(self._rt.plan.themes) if self._rt.plan else []
        gc = self._groq_complete_fn(groq_client) if groq_client is not None else None
        return generate_scorecard(
            jd,
            resume,
            themes,
            self.conversation_history,
            early_exit=early_exit,
            groq_complete=gc,
            ollama_chat=self._ollama_chat_fn(),
            groq_model=GROQ_MODEL,
            ollama_model=OLLAMA_MODEL,
        )

    def _structured_branch_reply(self, groq_client) -> Optional[str]:
        """
        If this user turn is fully handled without the main interviewer stream, return assistant text.
        Otherwise return None.

        Sets self._branch_outcome for callers:
        - terminal_report: full scorecard / early-exit text — print only in standalone; do not TTS.
        - terminal_notice: session already ended — print only; do not TTS.
        - none: (unused for non-None returns) normal branch content should be spoken (legacy).
        """
        self._branch_outcome = "none"

        if not self._structured_mode():
            return None
        self._ensure_plan(groq_client)
        if self._rt.plan is None:
            return None

        if self._rt.done:
            msg = (
                "This interview session is already complete. Thank you again for your time today—"
                "the hiring team will follow up if needed."
            )
            self._branch_outcome = "terminal_notice"
            return msg

        n = self._rt.num_questions_asked
        gc = self._groq_complete_fn(groq_client) if groq_client is not None else None
        dev_lines: list[str] = []

        if INTERVIEW_TERMINAL_SCORES and n >= 1 and n <= 15 and self._rt.plan is not None:
            q_prev = self._rt.plan.questions[n - 1]
            user_msg = self.conversation_history[-1].get("content", "")
            theme_i = (n - 1) // 3
            themes = self._rt.plan.themes
            theme = themes[theme_i] if theme_i < len(themes) else ""
            sc, rel_reason = score_interview_answer(
                q_prev,
                user_msg,
                theme=theme,
                groq_complete=gc,
                ollama_chat=self._ollama_chat_fn(),
                groq_model=GROQ_MODEL,
                ollama_model=OLLAMA_MODEL,
            )
            if sc >= 1:
                rs = rel_reason if rel_reason else "no reason returned"
                dev_lines.append(f"Relevance (Q{n}/15): {sc}/10 — {rs}")
            else:
                dev_lines.append(f"Relevance (Q{n}/15): unavailable (model did not return a score)")

        if n >= 15:
            text = self._scorecard_block(groq_client, early_exit=False)
            self._rt.done = True
            self._branch_outcome = "terminal_report"
            self._log_dev_panel(f"Interview metrics — after scripted answer Q{n}/15 (final)", dev_lines)
            return text

        if n >= 1 and n <= self._rt.gate_first_n:
            q_prev = self._rt.plan.questions[n - 1]
            user_msg = self.conversation_history[-1].get("content", "")
            resume_ex = (interview_documents.resume or "").strip()
            strike, gate_note = assess_phase_gate(
                q_prev,
                user_msg,
                resume_ex,
                groq_complete=gc,
                ollama_chat=self._ollama_chat_fn(),
                groq_model=GROQ_MODEL,
                ollama_model=OLLAMA_MODEL,
            )
            if strike:
                self._rt.strikes += 1
                gline = (
                    f"Phase-gate STRIKE: {self._rt.strikes}/{self._rt.strikes_to_end} "
                    f"(within first {self._rt.gate_first_n} scripted answers)"
                )
                if gate_note:
                    gline += f" — gate note: {gate_note}"
                dev_lines.append(gline)
                if self._rt.strikes < self._rt.strikes_to_end:
                    self._post_strike_redirect_pending = True
                    dev_lines.append(
                        "Policy: next interviewer reply = brief redirect + next planned question (TTS)."
                    )
            else:
                dev_lines.append(
                    f"Phase-gate OK — scripted answer {n}/{self._rt.gate_first_n} in gate window "
                    f"(strikes {self._rt.strikes}/{self._rt.strikes_to_end})"
                )

            self._log_dev_panel(f"Interview metrics — after scripted answer Q{n}/15", dev_lines)

            if self._rt.strikes >= self._rt.strikes_to_end:
                intro = (
                    "Thank you for your time today. We’ll conclude the technical portion here. "
                )
                card = self._scorecard_block(groq_client, early_exit=True)
                self._rt.done = True
                self._branch_outcome = "terminal_report"
                return intro + card

            return None

        if dev_lines:
            self._log_dev_panel(f"Interview metrics — after scripted answer Q{n}/15 (post gate window)", dev_lines)

        return None

    def _enqueue_tts_sentences(self, paragraph: str) -> None:
        """Split long assistant text into TTS-sized sentence chunks."""
        text = (paragraph or "").strip()
        if not text:
            return
        buf = ""
        for ch in text:
            buf += ch
            if ch in ".!?" and len(buf.strip()) > 8:
                chunk = buf.strip()
                if len(chunk) > 2:
                    self.state.tts_queue.put(chunk)
                buf = ""
        tail = buf.strip()
        if len(tail) > 2:
            self.state.tts_queue.put(tail)

    def complete_turn_sync_for_bridge(self) -> str:
        """
        Non-streaming reply for ai_bridge_server after the caller appended the user message
        to conversation_history.
        """
        groq_client = None
        if GROQ_API_KEY:
            from groq import Groq

            groq_client = Groq(api_key=GROQ_API_KEY)

        branch = self._structured_branch_reply(groq_client)
        if branch is not None:
            self._post_strike_redirect_pending = False
            kind = self._branch_outcome
            if kind == "terminal_report":
                self._print_terminal_report("CANDIDATE REPORT (ai_bridge / terminal log)", branch)
            elif kind == "terminal_notice":
                self._log_dev_panel("SESSION NOTICE (ai_bridge)", [branch])
            self.conversation_history.append({"role": "assistant", "content": branch})
            return branch

        request_messages = self._build_request_messages()
        content = ""

        if GROQ_API_KEY:
            try:
                from groq import Groq

                client = Groq(api_key=GROQ_API_KEY)
                completion = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=request_messages,
                    max_tokens=200,
                )
                content = completion.choices[0].message.content if completion.choices else ""
            except Exception:
                content = ""

        if not (content or "").strip():
            try:
                import ollama

                response = ollama.chat(
                    model=OLLAMA_MODEL, messages=request_messages, stream=False
                )
                content = response.get("message", {}).get("content", "")
            except Exception:
                content = ""

        text = (content or "").strip()
        used_fallback_only = False
        if not text:
            text = self._safe_interviewer_fallback()
            used_fallback_only = True
        elif self._is_forbidden_interviewer_output(text):
            text = self._safe_interviewer_fallback()
            used_fallback_only = True

        if not used_fallback_only:
            self.conversation_history.append({"role": "assistant", "content": text})
            if self._structured_mode() and self._rt.plan is not None and not self._rt.done:
                self._rt.num_questions_asked += 1

        if len(self.conversation_history) > (self.max_runtime_history_messages + 2):
            self.conversation_history = self.conversation_history[-self.max_runtime_history_messages :]

        self._post_strike_redirect_pending = False
        return text

    def start(self):
        """Worker loop for LLM response generation."""
        groq_client = None
        if GROQ_API_KEY:
            from groq import Groq

            groq_client = Groq(api_key=GROQ_API_KEY)
        import ollama

        def enqueue_spoken_error(text: str):
            try:
                if text and text.strip():
                    self.state.tts_queue.put(text.strip())
                self.state.tts_queue.put("<END_OF_TURN>")
            except Exception:
                pass

        while self.state.is_running:
            try:
                user_text = self.state.llm_queue.get(timeout=1.0)
                print(f"\n[You]: {user_text}")

                self.conversation_history.append({"role": "user", "content": user_text})

                branch = self._structured_branch_reply(groq_client)
                if branch is not None:
                    self._post_strike_redirect_pending = False
                    kind = self._branch_outcome
                    if kind == "terminal_report":
                        self.state.is_ai_speaking = False
                        self._print_terminal_report(
                            "FINAL CANDIDATE REPORT (terminal only — not spoken via TTS)",
                            branch,
                        )
                        self.conversation_history.append(
                            {
                                "role": "assistant",
                                "content": "[Interview ended — full report printed in terminal above.]",
                            }
                        )
                        if len(self.conversation_history) > (self.max_runtime_history_messages + 2):
                            self.conversation_history = self.conversation_history[
                                -self.max_runtime_history_messages :
                            ]
                        print("\n[Interview] Session finished. is_running=False (main loop will exit).\n", flush=True)
                        self.state.is_running = False
                        break
                    if kind == "terminal_notice":
                        self.state.is_ai_speaking = False
                        self._log_dev_panel("SESSION (already ended)", [branch])
                        self.conversation_history.append({"role": "assistant", "content": branch})
                        if len(self.conversation_history) > (self.max_runtime_history_messages + 2):
                            self.conversation_history = self.conversation_history[
                                -self.max_runtime_history_messages :
                            ]
                        print("\n[Interview] Session finished. is_running=False (main loop will exit).\n", flush=True)
                        self.state.is_running = False
                        break
                    self.state.is_ai_speaking = True
                    print(f"[AI]: {branch}\n")
                    self.conversation_history.append({"role": "assistant", "content": branch})
                    if len(self.conversation_history) > (self.max_runtime_history_messages + 2):
                        self.conversation_history = self.conversation_history[
                            -self.max_runtime_history_messages :
                        ]
                    self._enqueue_tts_sentences(branch)
                    self.state.tts_queue.put("<END_OF_TURN>")
                    self.state.is_ai_speaking = False
                    print("--- READY: START SPEAKING ---")
                    continue

                print("[AI]: ", end="", flush=True)

                self.state.interrupt_flag = False
                self.state.is_ai_speaking = True

                ai_text = ""
                sentence_buffer = ""

                try:
                    if GROQ_API_KEY:
                        try:
                            request_messages = self._build_request_messages()
                            stream = groq_client.chat.completions.create(
                                model=GROQ_MODEL,
                                messages=request_messages,
                                stream=True,
                                max_tokens=200,
                            )
                            for chunk in stream:
                                if self.state.interrupt_flag:
                                    self.state.is_ai_speaking = False
                                    print("\n[AI Interrupted by User]")
                                    break
                                word = chunk.choices[0].delta.content or ""
                                print(word, end="", flush=True)
                                ai_text += word
                                sentence_buffer += word
                                if any(p in word for p in [".", "!", "?", "\n"]):
                                    clean = sentence_buffer.strip()
                                    if len(clean) > 2:
                                        self.state.tts_queue.put(clean)
                                    sentence_buffer = ""
                        except Exception as groq_ex:
                            msg = str(groq_ex).lower()
                            is_rate_limited = (
                                ("429" in msg) or ("rate limit" in msg) or ("rate_limit" in msg)
                            )
                            if is_rate_limited:
                                print("\n[Groq rate-limited; falling back to Ollama]")
                            else:
                                print(f"\n[Groq Error]: {groq_ex}")

                            request_messages = self._build_request_messages()
                            response = ollama.chat(
                                model=OLLAMA_MODEL,
                                messages=request_messages,
                                stream=True,
                            )
                            for chunk in response:
                                if self.state.interrupt_flag:
                                    self.state.is_ai_speaking = False
                                    print("\n[AI Interrupted by User]")
                                    break
                                word = chunk["message"]["content"]
                                print(word, end="", flush=True)
                                ai_text += word
                                sentence_buffer += word
                                if any(p in word for p in [".", "!", "?", "\n"]):
                                    clean = sentence_buffer.strip()
                                    if len(clean) > 2:
                                        self.state.tts_queue.put(clean)
                                    sentence_buffer = ""
                    else:
                        request_messages = self._build_request_messages()
                        response = ollama.chat(
                            model=OLLAMA_MODEL, messages=request_messages, stream=True
                        )
                        for chunk in response:
                            if self.state.interrupt_flag:
                                self.state.is_ai_speaking = False
                                print("\n[AI Interrupted by User]")
                                break
                            word = chunk["message"]["content"]
                            print(word, end="", flush=True)
                            ai_text += word
                            sentence_buffer += word
                            if any(p in word for p in [".", "!", "?", "\n"]):
                                clean = sentence_buffer.strip()
                                if len(clean) > 2:
                                    self.state.tts_queue.put(clean)
                                sentence_buffer = ""

                except Exception as e:
                    print(f"\n[LLM Error]: {e}")
                    self.state.is_ai_speaking = False
                    self._post_strike_redirect_pending = False
                    enqueue_spoken_error("Sorry, I’m having trouble right now.")
                    continue

                if sentence_buffer.strip() and not self.state.interrupt_flag:
                    self.state.tts_queue.put(sentence_buffer.strip())

                print("\n")
                final_text = ai_text.strip()
                if final_text and self._is_forbidden_interviewer_output(final_text):
                    safe_text = self._safe_interviewer_fallback()
                    print("[AI Guard]: Replaced unsafe response with interviewer-safe fallback.")
                    self.state.tts_queue.put(safe_text)
                    self.state.tts_queue.put("<END_OF_TURN>")
                    self._post_strike_redirect_pending = False
                    print("--- READY: START SPEAKING ---")
                    continue

                self.state.tts_queue.put("<END_OF_TURN>")

                if ai_text.strip() and not self.state.interrupt_flag:
                    self.conversation_history.append({"role": "assistant", "content": ai_text})
                    if self._structured_mode() and self._rt.plan is not None and not self._rt.done:
                        self._rt.num_questions_asked += 1

                self._post_strike_redirect_pending = False

                if len(self.conversation_history) > (self.max_runtime_history_messages + 2):
                    self.conversation_history = self.conversation_history[
                        -self.max_runtime_history_messages :
                    ]

                print("--- READY: START SPEAKING ---")

            except queue.Empty:
                continue
            except Exception as e:
                print(f"\n[LLM Error]: {e}")
                print("--- READY: START SPEAKING --")
