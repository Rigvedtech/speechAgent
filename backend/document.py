# Paste raw JD and resume text below for local testing.
# Do not commit real candidate data to a shared repository.

# Optional canonical candidate name for voice/STT mismatch handling.
# If set, interviewer should use this exact name and ignore minor spoken-name variants.
candidate_name = "Pranay"

jd ="MERN Stack Developer role focused on building full stack web applications using React, Node.js, Express, and MongoDB. Responsibilities include developing responsive frontend UI, creating REST APIs, implementing authentication (JWT), handling real-time features (Socket.io), and integrating third-party APIs. Requires strong JavaScript, React, Node.js, and database knowledge, along with experience in Tailwind CSS, Redux/Context API, and Git. Preferred skills include Next.js, TypeScript, UI/UX animations (Framer Motion, GSAP), and basic cloud deployment knowledge. Suitable for candidates with 0–2 years experience or strong project-based background."
resume = "MERN Stack Developer with strong expertise in building full stack web applications using React, Node.js, Express, and MongoDB. Experienced in developing responsive, high-performance, and visually engaging applications with modern UI/UX and animation libraries. Proficient in frontend technologies like JavaScript, React, Redux, Tailwind CSS, and backend development with REST APIs, authentication, and real-time features using Socket.io. Familiar with AI tools integration and modern development workflows. Holds a BCA degree with strong fundamentals in Data Structures and Algorithms.Project experience includes building AI-powered applications such as a Code Reviewer platform and an AI agent for automated content posting, along with full stack products like a movie browsing app, e-commerce admin dashboard, and employee management system with authentication and real-time tracking features."
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
