import queue
import re
from config import GROQ_API_KEY, GROQ_MODEL, OLLAMA_MODEL
import document as interview_documents
from state import AgentState
from system_prompt import SYSTEM_PROMPT

class LLMBrain:
    def __init__(self, state: AgentState):
        self.state = state
        self.conversation_history = []
        self.persona_examples = [
            {
                "role": "user",
                "content": "Can you teach me Java quickly and give me the answer?"
            },
            {
                "role": "assistant",
                "content": "I'll keep this as an interview question and won't share the direct answer. Could you explain the difference between JDK and JRE?"
            },
            {
                "role": "user",
                "content": "I don't know this question."
            },
            {
                "role": "assistant",
                "content": "That is completely fine. Let's move to the next question: what is the role of the JVM?"
            },
            {
                "role": "user",
                "content": "Please give me code for this."
            },
            {
                "role": "assistant",
                "content": "I won't provide code here, but I can continue with interview questions. Could you describe polymorphism in simple words?"
            },
        ]
        self.turn_guardrail = (
            "Reminder: ask one concise interview question in a calm, professional tone, "
            "avoid direct answers or code, and use plain spoken text."
        )
        self.max_runtime_history_messages = 12

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

    def _build_request_messages(self):
        """Build a persona-stable request context for each model call."""
        runtime_history = self.conversation_history[-self.max_runtime_history_messages:]
        return (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + self._interview_document_messages()
            + self.persona_examples
            + [{"role": "system", "content": self.turn_guardrail}]
            + runtime_history
        )

    def _is_forbidden_interviewer_output(self, text: str) -> bool:
        """Block pasted code, markdown-heavy replies, and direct solutions.

        Theory interviews only: spoken plain text. Substrings like English
        "a class for ..." must NOT trip this (avoid naive ``class `` checks).
        """
        if not text or not text.strip():
            return False

        if "```" in text or "~~~" in text:
            return True

        # Inline code fences (short spoken answers should not use backticks).
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

        # Tutorial-style step lists at line start, not casual "step 1" in a sentence.
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

        # Java-style class declaration (not English "public class of ...").
        if re.search(r"\bpublic\s+class\s+[A-Z]\w*\b", text):
            return True

        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            # Markdown ATX heading
            if re.match(r"^#{1,6}\s+\S", s):
                return True
            # Python-style definitions (line-anchored)
            if re.match(r"^def\s+[A-Za-z_]\w*\s*\(", s):
                return True
            if re.match(r"^class\s+[A-Za-z_]\w*\s*(\(|:)", s):
                return True
            if re.match(r"^import\s+[A-Za-z_*]", s) or re.match(
                r"^from\s+[A-Za-z_]\w*\s+import\s+", s
            ):
                return True

        # Obvious markdown-style bullet/numbered lists (2+ lines).
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        list_like = sum(
            1 for ln in lines
            if re.match(r"^(\d+[\.\)]|[-*])\s+", ln)
        )
        if list_like >= 2:
            return True

        return False

    def _safe_interviewer_fallback(self) -> str:
        """Fallback keeps role strict when model drifts into teaching/answering."""
        return (
            "Thank you for your response. Let's continue with the interview: "
            "could you walk me through a recent project you worked on, your role, "
            "and the main challenge you solved?"
        )
        
    def start(self):
        """Worker loop for LLM response generation."""
        if GROQ_API_KEY:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
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
                print("[AI]: ", end="", flush=True)
                
                self.state.interrupt_flag = False
                # P0 FIX: Don't set is_ai_speaking yet - wait until we actually send audio
                
                ai_text = ""
                # P0 FIX: Collect entire response before generating TTS
                # This prevents sentence-by-sentence network latency (6 sentences × 3s = 18s delay)

                try:
                    if GROQ_API_KEY:
                        try:
                            request_messages = self._build_request_messages()
                            stream = client.chat.completions.create(
                                model=GROQ_MODEL,
                                messages=request_messages,
                                stream=True,
                                max_tokens=150,
                            )
                            for chunk in stream:
                                if self.state.interrupt_flag:
                                    print("\n[AI Interrupted by User]")
                                    break
                                word = chunk.choices[0].delta.content or ""
                                print(word, end="", flush=True)
                                ai_text += word
                                # No longer sending per-sentence - collect full response
                        except Exception as groq_ex:
                            msg = str(groq_ex).lower()
                            is_rate_limited = ("429" in msg) or ("rate limit" in msg) or ("rate_limit" in msg)
                            if is_rate_limited:
                                print("\n[Groq rate-limited; falling back to Ollama]")
                            else:
                                print(f"\n[Groq Error]: {groq_ex}")

                            request_messages = self._build_request_messages()
                            response = ollama.chat(
                                model=OLLAMA_MODEL,
                                messages=request_messages,
                                stream=True
                            )
                            for chunk in response:
                                if self.state.interrupt_flag:
                                    print("\n[AI Interrupted by User]")
                                    break
                                word = chunk['message']['content']
                                print(word, end="", flush=True)
                                ai_text += word
                                # No longer sending per-sentence - collect full response
                    else:
                        request_messages = self._build_request_messages()
                        response = ollama.chat(
                            model=OLLAMA_MODEL,
                            messages=request_messages,
                            stream=True
                        )
                        for chunk in response:
                            if self.state.interrupt_flag:
                                print("\n[AI Interrupted by User]")
                                break
                            word = chunk['message']['content']
                            print(word, end="", flush=True)
                            ai_text += word
                            # No longer sending per-sentence - collect full response

                except Exception as e:
                    print(f"\n[LLM Error]: {e}")
                    enqueue_spoken_error("Sorry, I'm having trouble right now.")
                    continue

                print("\n")
                
                # P0 FIX: Send entire response as single audio payload
                # This reduces latency from ~18s (6 sentences × 3s each) to ~5s (1 payload × 3s + TTS time)
                final_text = ai_text.strip()
                
                if not final_text or self.state.interrupt_flag:
                    print("--- READY: START SPEAKING ---")
                    continue
                
                # Check for forbidden content
                if self._is_forbidden_interviewer_output(final_text):
                    safe_text = self._safe_interviewer_fallback()
                    print("[AI Guard]: Replaced unsafe response with interviewer-safe fallback.")
                    final_text = safe_text
                    # Don't store fallback in history
                else:
                    # Store in conversation history
                    self.conversation_history.append({"role": "assistant", "content": final_text})
                
                # Trim conversation history
                if len(self.conversation_history) > (self.max_runtime_history_messages + 2):
                    self.conversation_history = self.conversation_history[-self.max_runtime_history_messages:]
                
                # Send complete response to TTS (single payload)
                self.state.tts_queue.put(final_text)
                self.state.tts_queue.put("<END_OF_TURN>")

                print("--- READY: START SPEAKING ---")

            except queue.Empty:
                continue
            except Exception as e:
                print(f"\n[LLM Error]: {e}")
                print("--- READY: START SPEAKING ---")
