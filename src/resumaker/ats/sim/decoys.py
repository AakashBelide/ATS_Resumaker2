"""Decoy resumes = the 'other applicants' in the pool (Phase 3 ranking test).

Hand-written plaintext, varying in relevance to an AI-Orchestration/AI-Engineer JD,
so we can verify our tailored resume ranks ABOVE them in a recruiter/BM25 search.
Kept deliberately realistic (not strawmen): adjacent, competent candidates.
"""

DECOYS: list[tuple[str, str]] = [
    ("decoy_backend_swe",
     "Senior Software Engineer. Built scalable backend microservices in Java and "
     "Spring Boot, REST APIs, PostgreSQL, Kafka event pipelines, and CI/CD on AWS "
     "ECS. Led a team of 4, improved API latency by 40%. Docker, Kubernetes, "
     "Terraform. Computer Science degree."),
    ("decoy_data_analyst",
     "Data Analyst. Built dashboards in Tableau and Power BI, wrote complex SQL "
     "queries, performed A/B testing and cohort analysis, automated Excel reporting, "
     "and presented insights to stakeholders. Some Python (pandas). Statistics minor."),
    ("decoy_frontend_dev",
     "Frontend Engineer. Built responsive web apps with React, TypeScript, Next.js, "
     "Redux, and Tailwind CSS. Improved Lighthouse performance, implemented design "
     "systems, and shipped accessible UI components. Jest testing, Vercel deploys."),
    ("decoy_ml_researcher",
     "Machine Learning Researcher. Published papers on transformer architectures and "
     "computer vision. Trained deep learning models in PyTorch, ran experiments on "
     "GPU clusters, and benchmarked on ImageNet. Strong math and research background; "
     "limited production deployment experience."),
    ("decoy_newgrad_swe",
     "New Grad Software Engineer. Coursework in data structures, algorithms, and "
     "databases. Internship building a CRUD web app with Python Flask and MySQL. "
     "Familiar with Git and basic cloud. Eager to learn AI/ML."),
    ("decoy_de_generalist",
     "Data Engineer. Built ETL pipelines with Airflow and Spark, managed Snowflake "
     "and BigQuery warehouses, and modeled data with dbt. Batch and streaming "
     "ingestion. Python and SQL. No LLM or agent experience."),
]
