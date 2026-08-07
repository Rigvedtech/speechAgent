-- Expand coding domain languages beyond python/javascript.

ALTER TABLE coding_domains DROP CONSTRAINT IF EXISTS coding_domains_language_valid;

ALTER TABLE coding_domains
    ADD CONSTRAINT coding_domains_language_valid CHECK (
        language IN (
            'python',
            'javascript',
            'typescript',
            'java',
            'cpp',
            'csharp',
            'go',
            'ruby',
            'php',
            'kotlin',
            'rust',
            'swift'
        )
    );
