# Paste raw JD and resume text below for local testing.
# Do not commit real candidate data to a shared repository.

# Optional canonical candidate name for voice/STT mismatch handling.
# If set, interviewer should use this exact name and ignore minor spoken-name variants.
candidate_name = "Payal"

jd = "Senior Full Stack Software Engineer role focused on building scalable Java/Spring Boot microservices and high-performance applications in fintech and banking. Requires strong experience in REST APIs, databases, cloud (AWS/Azure), and DevOps tools, along with knowledge of CI/CD, system design, and Agile practices. Ideal candidate has experience in UPI/payment systems, performance optimization, and leading or mentoring teams."
resume = "Senior Full Stack Software Engineer with 6+ years of experience in fintech and banking, specializing in building scalable Java/Spring Boot microservices and high-performance systems with 99.98% uptime. Strong expertise in backend development, REST APIs, databases, and cloud technologies, with hands-on experience in Databricks, Apache Spark, and data-driven architectures. Proven track record of improving system performance, reducing response times, and optimizing CI/CD processes, along with leading Agile teams and mentoring developers to deliver reliable, enterprise-grade solutions. :contentReference[oaicite:0]{index=0}"
# Shown to the model whenever jd or resume is non-empty.
GROUNDING_RULES = (
    "Grounding rules for this interview:\n"
    "- Base job-fit and requirement questions only on the JOB DESCRIPTION (JD) section above.\n"
    "- Base experience, company, project, and skill questions only on facts that appear in the "
    "CANDIDATE RESUME section above. Name companies and projects exactly as written there.\n"
    "- Do not invent employers, titles, dates, technologies, or projects that are not in the resume text.\n"
    "- If the resume or JD does not mention something, do not assume it; ask a neutral clarification "
    "or choose a different question.\n"
    "- Mix JD-aligned questions with resume-specific follow-ups (role, impact, challenges) so the "
    "conversation feels like a real interview.\n"
    "- Voice/STT tolerance: never accuse the candidate of mistakes in their self-introduction due to "
    "spelling/pronunciation differences. Treat near-sounding names as ASR noise."
)
