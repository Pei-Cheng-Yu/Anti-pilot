"""add pgvector memory retrieval

Revision ID: f2b7c9d8e1a4
Revises: 9a7f1d3c2b6e
Create Date: 2026-05-04 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2b7c9d8e1a4"
down_revision: Union[str, Sequence[str], None] = "9a7f1d3c2b6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS coding_problem_attempts (
            attempt_id VARCHAR NOT NULL,
            user_id VARCHAR NOT NULL,
            skillpath_id VARCHAR NOT NULL,
            content_id VARCHAR NOT NULL,
            submitted_code TEXT NOT NULL,
            language VARCHAR NOT NULL,
            correctness VARCHAR NOT NULL,
            feedback_summary TEXT NOT NULL,
            detected_concepts TEXT[] NOT NULL,
            detected_mistakes TEXT[] NOT NULL,
            compile_error TEXT,
            runtime_error TEXT,
            score FLOAT,
            test_results JSONB NOT NULL,
            submitted_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_coding_problem_attempts PRIMARY KEY (attempt_id),
            CONSTRAINT fk_coding_problem_attempts_user_id_users
                FOREIGN KEY(user_id) REFERENCES users (user_id),
            CONSTRAINT fk_coding_problem_attempts_skillpath_id_skillpaths
                FOREIGN KEY(skillpath_id) REFERENCES skillpaths (skillpath_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_mastery_states (
            id SERIAL NOT NULL,
            user_id VARCHAR NOT NULL,
            skillpath_id VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            mastery_score FLOAT NOT NULL,
            successful_attempts INTEGER NOT NULL,
            failed_attempts INTEGER NOT NULL,
            strong_concepts TEXT[] NOT NULL,
            weak_concepts TEXT[] NOT NULL,
            last_attempt_at TIMESTAMP WITHOUT TIME ZONE,
            last_updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_skill_mastery_states PRIMARY KEY (id),
            CONSTRAINT fk_skill_mastery_states_user_id_users
                FOREIGN KEY(user_id) REFERENCES users (user_id),
            CONSTRAINT uq_skill_mastery_states_user_id UNIQUE (user_id, skillpath_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learner_memory_notes (
            memory_id VARCHAR NOT NULL,
            user_id VARCHAR NOT NULL,
            memory_type VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            summary TEXT NOT NULL,
            tags TEXT[] NOT NULL,
            linked_concepts TEXT[] NOT NULL,
            linked_skillpath_ids TEXT[] NOT NULL,
            linked_content_ids TEXT[] NOT NULL,
            evidence_attempt_ids TEXT[] NOT NULL,
            embedding vector(3072),
            search_text TEXT DEFAULT '' NOT NULL,
            salience_score FLOAT NOT NULL,
            status VARCHAR NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            last_seen_at TIMESTAMP WITHOUT TIME ZONE,
            last_used_at TIMESTAMP WITHOUT TIME ZONE,
            CONSTRAINT pk_learner_memory_notes PRIMARY KEY (memory_id),
            CONSTRAINT fk_learner_memory_notes_user_id_users
                FOREIGN KEY(user_id) REFERENCES users (user_id)
        )
        """
    )
    op.execute(
        "ALTER TABLE learner_memory_notes "
        "ADD COLUMN IF NOT EXISTS search_text TEXT NOT NULL DEFAULT ''"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF (
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                WHERE c.relname = 'learner_memory_notes'
                  AND a.attname = 'embedding'
                  AND NOT a.attisdropped
            ) = 'jsonb' THEN
                ALTER TABLE learner_memory_notes
                ALTER COLUMN embedding TYPE vector(3072)
                USING (
                    CASE
                        WHEN embedding IS NULL THEN NULL
                        WHEN jsonb_typeof(embedding) = 'array'
                         AND jsonb_array_length(embedding) = 3072
                        THEN embedding::text::vector
                        ELSE NULL
                    END
                );
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learner_memory_notes_embedding
        ON learner_memory_notes
        USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learner_memory_notes_search_text
        ON learner_memory_notes
        USING gin (to_tsvector('english', search_text))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learner_memory_notes_concepts
        ON learner_memory_notes USING gin (linked_concepts)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learner_memory_notes_skillpaths
        ON learner_memory_notes USING gin (linked_skillpath_ids)
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_learner_memory_notes_skillpaths", table_name="learner_memory_notes"
    )
    op.drop_index("ix_learner_memory_notes_concepts", table_name="learner_memory_notes")
    op.drop_index(
        "ix_learner_memory_notes_search_text", table_name="learner_memory_notes"
    )
    op.drop_index(
        "ix_learner_memory_notes_embedding", table_name="learner_memory_notes"
    )
    op.execute(
        """
        ALTER TABLE learner_memory_notes
        ALTER COLUMN embedding TYPE JSONB
        USING (
            CASE
                WHEN embedding IS NULL THEN NULL
                ELSE embedding::text::jsonb
            END
        )
        """
    )
    op.drop_column("learner_memory_notes", "search_text")
