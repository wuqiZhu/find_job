CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(100) UNIQUE NOT NULL,
    source VARCHAR(50) NOT NULL DEFAULT 'boss',
    company VARCHAR(200) NOT NULL,
    role VARCHAR(300) NOT NULL,
    location VARCHAR(100),
    salary VARCHAR(100),
    experience VARCHAR(100),
    education VARCHAR(50),
    jd_text TEXT,
    jd_skills TEXT,
    url VARCHAR(500),
    boss_title VARCHAR(100),
    boss_online BOOLEAN DEFAULT false,
    score DECIMAL(5,2),
    score_raw VARCHAR(20),
    archetype VARCHAR(100),
    legitimacy VARCHAR(50),
    report_text TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scored_at TIMESTAMP,
    notified_at TIMESTAMP,
    submitted_at TIMESTAMP,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS job_logs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(100),
    action VARCHAR(50) NOT NULL,
    detail TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_job_id ON jobs(job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_logs_job_id ON job_logs(job_id);
