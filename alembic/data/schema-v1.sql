CREATE TABLE users (
	id UUID NOT NULL,
	email VARCHAR(254) NOT NULL,
	password_hash VARCHAR(512) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (email)
);

CREATE TABLE catalog_items (
	id VARCHAR(32) NOT NULL,
	category VARCHAR(16) NOT NULL,
	content JSONB NOT NULL,
	PRIMARY KEY (id),
	CHECK (category IN ('vocabulary', 'listening'))
);

CREATE INDEX ix_catalog_items_category ON catalog_items (category);

CREATE TABLE auth_attempts (
	id SERIAL NOT NULL,
	scope VARCHAR(64) NOT NULL,
	"window" INTEGER NOT NULL,
	count INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (scope, "window")
);

CREATE TABLE sessions (
	token_hash VARCHAR(64) NOT NULL,
	user_id UUID NOT NULL,
	csrf_hash VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (token_hash),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

CREATE INDEX ix_sessions_expires_at ON sessions (expires_at);

CREATE TABLE progress (
	user_id UUID NOT NULL,
	entry_id VARCHAR(32) NOT NULL,
	category VARCHAR(16) NOT NULL,
	status VARCHAR(16) NOT NULL,
	attempts INTEGER NOT NULL,
	correct INTEGER NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (user_id, entry_id),
	CHECK (attempts >= 0 AND correct >= 0 AND correct <= attempts),
	CHECK (status IN ('mastered', 'review', 'unseen')),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(entry_id) REFERENCES catalog_items (id)
);

CREATE TABLE study_events (
	user_id UUID NOT NULL,
	event_id UUID NOT NULL,
	entry_id VARCHAR(32) NOT NULL,
	request JSONB NOT NULL,
	correct BOOLEAN,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (user_id, event_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(entry_id) REFERENCES catalog_items (id)
);

CREATE TABLE progress_imports (
	user_id UUID NOT NULL,
	import_id UUID NOT NULL,
	payload_hash VARCHAR(64) NOT NULL,
	PRIMARY KEY (user_id, import_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
