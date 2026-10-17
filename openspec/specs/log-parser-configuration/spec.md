# Log parser configuration Specification

## Purpose

Define default player and stopping log observations, preserve achievement text and
message boundaries, and retain administrator-owned settings when defaults change.
Connection attempts and diagnostic fragments must not become player history.

## Requirements

### Requirement: Default departures require a player message

The default leave rule SHALL recognize a structured bracketed log header followed
by a single non-whitespace player name and `lost connection: ` with its reason.
It SHALL preserve the player name and complete reason of ordinary departures.
It SHALL reject connection addresses, GameProfile objects, bare IPv4 addresses,
whitespace-containing names and chat-wrapped or narrative departure text.

#### Scenario: Ordinary departure
- **WHEN** a structured server log contains a single-name player departure
- **THEN** the observer produces that player's departure with the original reason

#### Scenario: Connection attempt ends while the player is online
- **WHEN** a same-name connection attempt ends with a parenthesized address or
  GameProfile subject while the player has an existing online session
- **THEN** that line does not produce a player departure or close the session

#### Scenario: Unsupported or forged subjects
- **WHEN** a candidate departure contains only an address, a bare IPv4 subject,
  a whitespace-containing name, or a chat/narrative wrapper
- **THEN** the default rule does not produce a player departure

### Requirement: Saved parser values survive default changes

Updating application defaults SHALL NOT replace explicitly stored parser values,
including scalar values and pattern lists equal to previous defaults. New
installations and absent fields SHALL use current defaults. Administrators SHALL
retain the existing configuration save flow to adopt a different value explicitly.

#### Scenario: Upgrade with a stored old default or custom rule
- **WHEN** saved parser settings contain an old default or custom leave rule
  and the application loads a newer schema
- **THEN** the saved rule and other explicitly configured values remain intact

#### Scenario: New or missing leave configuration
- **WHEN** the leave field has not been explicitly stored
- **THEN** the current default rule is used

#### Scenario: Stored scalar and list patterns
- **WHEN** saved login, chat, stopping and achievement settings contain old defaults
  or custom rules and current defaults change
- **THEN** every explicitly stored scalar and list value remains unchanged
- **AND** only absent fields receive current defaults

### Requirement: Default achievement announcements preserve display text

The default rules SHALL recognize structured task, goal, challenge and legacy
achievement announcements and retain their complete player display text for the
existing known-player attribution and their nonempty title for history. Supported
display text SHALL exclude angle brackets and embedded escape codes. The rules
SHALL consume ANSI SGR sequences surrounding display text
and titles without including those sequences in the resulting achievement.
Display text MAY contain titles and spaces; account names containing whitespace
remain unsupported. Titles SHALL retain internal square brackets and angle
brackets. Empty titles and the unusable display text `<>` SHALL NOT produce an
achievement.

#### Scenario: Four achievement announcement forms
- **WHEN** a known player has a structured announcement using `has made the
  advancement`, `has reached the goal`, `has completed the challenge` or
  `has just earned the achievement`
- **THEN** the player's achievement history records the announced title
- **AND** repeating the same announcement preserves existing title deduplication

#### Scenario: Colored display text and nested title punctuation
- **WHEN** an announcement surrounds a titled player display or a title containing
  square or angle brackets with ANSI SGR codes
- **THEN** player attribution receives the full display text and the title retains
  its punctuation without the surrounding ANSI codes

#### Scenario: Empty title or unusable display
- **WHEN** an announcement has an empty bracketed title or display text `<>`
- **THEN** no player achievement is recorded from that line

#### Scenario: Achievement wording inside chat
- **WHEN** a player chat message quotes an achievement announcement
- **THEN** the line remains a chat observation and does not award an achievement

### Requirement: Default chat recognition starts at the message boundary

The default chat rule SHALL recognize direct chat bodies following structured
bracketed log headers, including logger blocks containing one nested bracket
level and the optional `[Not Secure]` prefix. It SHALL preserve existing
non-whitespace chat-name extraction and the message content. Diagnostic text
containing angle-bracket fragments after other message text SHALL NOT produce
player chat messages.

#### Scenario: Nested logger header and security marker
- **WHEN** a direct player chat follows a structured log header whose logger block
  contains nested brackets, with or without the security marker
- **THEN** the observer records the player and message using the existing chat flow

#### Scenario: Diagnostic angle-bracket fragments
- **WHEN** a diagnostic message contains method, resource or recipe identifiers in
  angle brackets after diagnostic text
- **THEN** the line does not add a player message or publish a player-chat event

### Requirement: Default login recognition preserves known server variants

The default join rule SHALL require a single non-whitespace player name followed
by a bracketed connection description and a complete login message. It SHALL
support slash-prefixed addresses including IPv6, `IP hidden`, `local`, optional
coordinates, and the known Sponge `in world(number)` and `in DIMnumber(number)`
suffixes. Narrative or chat-wrapped login text and whitespace-containing account
names SHALL NOT produce a join observation. Ordinary joined-game broadcasts SHALL
NOT become an additional join event source.

#### Scenario: Address and Sponge variants
- **WHEN** a known player logs in using a supported connection description and
  optional Sponge dimension and coordinate text
- **THEN** the observer opens that player's session through the existing join flow

#### Scenario: Unsupported name and quoted login
- **WHEN** the login subject contains whitespace or a player quotes a login message
- **THEN** the default rule does not open a session from that text

### Requirement: Default stopping recognition preserves known messages

The default stopping rule SHALL recognize structured ordinary stopping messages,
the observed Paper stopping message with its thread-death disclaimer, and missing
startup-script messages ending in `Stopping server.`. It SHALL retain closure of
the observed server's open sessions and the existing stopping event. Chat or
narrative text quoting stopping wording SHALL NOT trigger that behavior. A
stopping observation SHALL NOT assert that the process has already exited.

#### Scenario: Known stopping variants
- **WHEN** one of the supported stopping bodies is observed while players have
  open sessions on that server
- **THEN** those sessions are closed and the stopping event remains observable

#### Scenario: Stopping text inside a chat message
- **WHEN** a player chat message quotes `Stopping server`
- **THEN** the player's session remains open and no stopping event is published
