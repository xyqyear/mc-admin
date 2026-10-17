## Purpose

Define default log departure recognition and preserve administrator-owned parser
settings when application defaults change, so connection attempts cannot silently
become player session departures.

## ADDED Requirements

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
including values equal to the previous default. New installations and absent
fields SHALL use current defaults. Administrators SHALL retain the existing
configuration save flow to adopt a different value explicitly.

#### Scenario: Upgrade with a stored old default or custom rule
- **WHEN** saved parser settings contain an old default or custom leave rule
  and the application loads a newer schema
- **THEN** the saved rule and other explicitly configured values remain intact

#### Scenario: New or missing leave configuration
- **WHEN** the leave field has not been explicitly stored
- **THEN** the current default rule is used
