BEGIN TRANSACTION;
CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL, 
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO "alembic_version" VALUES('2026060500');
CREATE TABLE cronjob (
	id INTEGER NOT NULL, 
	cronjob_id VARCHAR(255) NOT NULL, 
	identifier VARCHAR(100) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	cron VARCHAR(100) NOT NULL, 
	second VARCHAR(20), 
	params_json TEXT NOT NULL, 
	execution_count INTEGER NOT NULL, 
	is_system BOOLEAN NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
INSERT INTO "cronjob" VALUES(701,'synthetic-restart','server_restart','restart-synthetic-survival','0 5 * * *',NULL,'{"server_id":"synthetic-survival"}',1,0,'PAUSED','2026-09-01 00:00:00','2026-09-01 00:00:00');
CREATE TABLE cronjob_execution (
	id INTEGER NOT NULL, 
	cronjob_id VARCHAR(255) NOT NULL, 
	execution_id VARCHAR(50) NOT NULL, 
	started_at DATETIME NOT NULL, 
	ended_at DATETIME, 
	duration_ms INTEGER, 
	status VARCHAR(9) NOT NULL, 
	messages_json TEXT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (execution_id)
);
INSERT INTO "cronjob_execution" VALUES(801,'synthetic-restart','synthetic-execution','2026-09-01 00:00:00','2026-09-01 00:00:01',1000,'COMPLETED','["Synthetic completed restart"]');
CREATE TABLE default_variable_config (
	id INTEGER NOT NULL, 
	variable_definitions_json TEXT NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE dynamic_config (
	id INTEGER NOT NULL, 
	module_name VARCHAR(100) NOT NULL, 
	config_data JSON NOT NULL, 
	config_schema_version VARCHAR(50) NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
INSERT INTO "dynamic_config" VALUES(901,'world','{"dimension_labels":{".":"Synthetic world"}}','1.0.0','2026-09-01 00:00:00');
CREATE TABLE player (
	player_db_id INTEGER NOT NULL, 
	uuid VARCHAR(32) NOT NULL, 
	current_name VARCHAR(16) NOT NULL, 
	skin_data BLOB, 
	avatar_data BLOB, 
	last_skin_update DATETIME, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (player_db_id)
);
INSERT INTO "player" VALUES(301,'123456781234423482341234567890ab','FixturePlayer',NULL,NULL,NULL,'2026-09-01 00:00:00');
CREATE TABLE player_achievement (
	achievement_id INTEGER NOT NULL, 
	player_db_id INTEGER NOT NULL, 
	server_db_id INTEGER NOT NULL, 
	achievement_name VARCHAR(255) NOT NULL, 
	earned_at DATETIME NOT NULL, 
	PRIMARY KEY (achievement_id)
);
INSERT INTO "player_achievement" VALUES(601,301,101,'minecraft:story/root','2026-09-01 00:00:00');
CREATE TABLE player_chat_message (
	message_id INTEGER NOT NULL, 
	player_db_id INTEGER NOT NULL, 
	server_db_id INTEGER NOT NULL, 
	message_text TEXT NOT NULL, 
	sent_at DATETIME NOT NULL, 
	PRIMARY KEY (message_id)
);
INSERT INTO "player_chat_message" VALUES(501,301,101,'Synthetic retained chat','2026-09-01 00:00:00');
CREATE TABLE player_session (
	session_id INTEGER NOT NULL, 
	player_db_id INTEGER NOT NULL, 
	server_db_id INTEGER NOT NULL, 
	joined_at DATETIME NOT NULL, 
	left_at DATETIME, 
	duration_seconds INTEGER, 
	PRIMARY KEY (session_id)
);
INSERT INTO "player_session" VALUES(401,301,101,'2026-09-01 00:00:00','2026-09-01 00:01:00',60);
INSERT INTO "player_session" VALUES(402,301,101,'2026-09-01 00:00:00',NULL,NULL);
CREATE TABLE restoration (
	id VARCHAR(32) NOT NULL, 
	server_id VARCHAR(100) NOT NULL, 
	type VARCHAR(9) NOT NULL, 
	source_snapshot_id VARCHAR(64) NOT NULL, 
	safety_snapshot_id VARCHAR(64), 
	selection_json TEXT NOT NULL, 
	is_rollback BOOLEAN NOT NULL, 
	initiated_by_user_id INTEGER, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME, 
	status VARCHAR(11) NOT NULL, 
	error_message TEXT, 
	PRIMARY KEY (id)
);
INSERT INTO "restoration" VALUES('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','synthetic-survival','WORLD','1111111111111111111111111111111111111111111111111111111111111111','2222222222222222222222222222222222222222222222222222222222222222','{"type":"world","world":"world"}',0,11,'2026-09-01 00:00:00','2026-09-01 00:00:02','SUCCEEDED',NULL);
CREATE TABLE self_check_finding (
	id INTEGER NOT NULL, 
	run_id VARCHAR(32) NOT NULL, 
	check_id VARCHAR(100) NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	severity VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	server_id VARCHAR(100), 
	title VARCHAR(255) NOT NULL, 
	message TEXT NOT NULL, 
	evidence_json TEXT NOT NULL, 
	remediation_json TEXT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE self_check_run (
	id VARCHAR(32) NOT NULL, 
	"trigger" VARCHAR(32) NOT NULL, 
	scope VARCHAR(20) NOT NULL, 
	check_id VARCHAR(100), 
	status VARCHAR(32) NOT NULL, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME NOT NULL, 
	summary_json TEXT NOT NULL, 
	requested_by_user_id INTEGER, 
	error_message TEXT, 
	PRIMARY KEY (id)
);
CREATE TABLE server (
	id INTEGER NOT NULL, 
	server_id VARCHAR(100) NOT NULL, 
	status VARCHAR(7) NOT NULL, 
	template_id INTEGER, 
	template_snapshot_json TEXT, 
	variable_values_json TEXT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
INSERT INTO "server" VALUES(101,'synthetic-survival','ACTIVE',201,'{"template_id": 201, "template_name": "synthetic-template", "yaml_template": "services:\n  mc:\n    image: itzg/minecraft-server:java25\n    container_name: mc-${SERVER_NAME}\n    ports: [''25565:25565'', ''25575:25575'']\n    environment: {VERSION: ''1.21.11'', SERVER_PORT: ''25565''}\n", "variable_definitions": [], "snapshot_time": "2026-09-01T00:00:00+00:00"}','{"SERVER_NAME":"synthetic-survival"}','2026-09-01 00:00:00','2026-09-01 00:00:00');
INSERT INTO "server" VALUES(102,'synthetic-retired','REMOVED',201,'{"template_id": 201, "template_name": "synthetic-template", "yaml_template": "services:\n  mc:\n    image: itzg/minecraft-server:java25\n    container_name: mc-${SERVER_NAME}\n    ports: [''25565:25565'', ''25575:25575'']\n    environment: {VERSION: ''1.21.11'', SERVER_PORT: ''25565''}\n", "variable_definitions": [], "snapshot_time": "2026-09-01T00:00:00+00:00"}','{"SERVER_NAME":"synthetic-survival"}','2026-09-01 00:00:00','2026-09-01 00:00:00');
CREATE TABLE server_template (
	id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	yaml_template TEXT NOT NULL, 
	variable_definitions_json TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
INSERT INTO "server_template" VALUES(201,'synthetic-template','Synthetic release fixture','services:
  mc:
    image: itzg/minecraft-server:java25
    container_name: mc-${SERVER_NAME}
    ports: [''25565:25565'', ''25575:25575'']
    environment: {VERSION: ''1.21.11'', SERVER_PORT: ''25565''}
','[]','2026-09-01 00:00:00','2026-09-01 00:00:00');
CREATE TABLE system_heartbeat (
	id INTEGER NOT NULL, 
	timestamp DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE user (
	id INTEGER, 
	username VARCHAR(50) NOT NULL, 
	hashed_password VARCHAR(255) NOT NULL, 
	role VARCHAR(5) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
INSERT INTO "user" VALUES(11,'synthetic-owner','not-a-valid-password-hash','OWNER','2026-09-01 00:00:00');
CREATE UNIQUE INDEX ix_user_username ON user (username);
CREATE UNIQUE INDEX ix_dynamic_config_module_name ON dynamic_config (module_name);
CREATE INDEX ix_cronjob_identifier ON cronjob (identifier);
CREATE UNIQUE INDEX ix_cronjob_cronjob_id ON cronjob (cronjob_id);
CREATE INDEX ix_cronjob_execution_cronjob_id ON cronjob_execution (cronjob_id);
CREATE INDEX idx_self_check_run_scope_check_finished_id ON self_check_run (scope, check_id, finished_at, id);
CREATE INDEX idx_self_check_run_scope_finished_id ON self_check_run (scope, finished_at, id);
CREATE INDEX ix_self_check_run_finished_at ON self_check_run (finished_at);
CREATE INDEX idx_self_check_finding_run ON self_check_finding (run_id);
CREATE INDEX ix_server_server_id ON server (server_id);
CREATE UNIQUE INDEX ix_server_template_name ON server_template (name);
CREATE UNIQUE INDEX ix_player_uuid ON player (uuid);
CREATE INDEX idx_player_session_player_time ON player_session (player_db_id, joined_at);
CREATE INDEX idx_player_session_server_online ON player_session (server_db_id, left_at);
CREATE INDEX idx_player_session_server_time ON player_session (server_db_id, joined_at);
CREATE INDEX ix_player_session_player_db_id ON player_session (player_db_id);
CREATE INDEX idx_player_session_player_left_at ON player_session (player_db_id, left_at);
CREATE INDEX idx_player_session_player_server_online ON player_session (player_db_id, server_db_id, left_at);
CREATE INDEX ix_player_session_server_db_id ON player_session (server_db_id);
CREATE INDEX ix_player_chat_message_player_db_id ON player_chat_message (player_db_id);
CREATE INDEX idx_player_chat_player_time ON player_chat_message (player_db_id, sent_at);
CREATE INDEX idx_player_chat_server_time ON player_chat_message (server_db_id, sent_at);
CREATE INDEX ix_player_chat_message_server_db_id ON player_chat_message (server_db_id);
CREATE INDEX ix_player_achievement_player_db_id ON player_achievement (player_db_id);
CREATE INDEX idx_player_achievement_player_time ON player_achievement (player_db_id, earned_at);
CREATE UNIQUE INDEX idx_player_achievement_unique ON player_achievement (player_db_id, server_db_id, achievement_name);
CREATE INDEX ix_player_achievement_server_db_id ON player_achievement (server_db_id);
CREATE INDEX idx_player_achievement_server_time ON player_achievement (server_db_id, earned_at);
CREATE INDEX idx_player_achievement_time ON player_achievement (earned_at);
CREATE INDEX ix_restoration_server_id ON restoration (server_id);
COMMIT;
