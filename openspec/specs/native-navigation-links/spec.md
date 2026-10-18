# Native navigation links Specification

## Purpose

Allow application navigation and search results to use native browser link
behavior while preserving source-page state and existing action boundaries.

## Requirements

### Requirement: Fixed navigation supports native browser actions

Visible fixed-destination navigation entries SHALL expose real destination links.
Ordinary primary clicks SHALL retain current-page navigation, while middle and
modified clicks SHALL retain native browser behavior. Navigation entries SHALL
retain their existing appearance, active-state rules and permission visibility.
Authentication redirects, history-back and mutation completion SHALL retain their
existing action semantics.

#### Scenario: Sidebar navigation and native new tab
- **WHEN** a user opens a sidebar destination using the middle button or a
  new-tab modifier
- **THEN** the destination opens using native browser navigation
- **AND** the source page retains its URL and sidebar expansion state

#### Scenario: Ordinary navigation and action controls
- **WHEN** a user follows a fixed destination normally
- **THEN** the current page navigates and the existing active-state rules apply
- **AND** group toggles, theme, logout and mutation controls remain actions

#### Scenario: Permission-dependent destination
- **WHEN** a navigation entry is unavailable to the current role
- **THEN** it remains unavailable and opening another tab does not bypass route
  authentication or server authorization

#### Scenario: File directory navigation
- **WHEN** a user opens a breadcrumb ancestor, parent directory or directory name
- **THEN** its destination opens that directory without a filename filter
- **AND** native new-tab navigation retains the source filter and selection
- **AND** ordinary navigation clears the source selection

#### Scenario: Error recovery destination
- **WHEN** a user follows the error fallback's home link normally
- **THEN** the application reloads the home document for recovery
- **AND** native new-tab link actions remain available

### Requirement: Search links reuse captured result destinations

Advanced-search result names SHALL expose links using the path and criteria that
produced the displayed results. File results SHALL navigate to their parent
directory with the filename as a literal filter; actual directory matches SHALL
open that directory without a filter; structural parent nodes SHALL retain the
executed regular expression. Special characters SHALL survive URL encoding.
Editing an unsubmitted search draft SHALL NOT change those result destinations.

#### Scenario: File result and special characters
- **WHEN** a file result contains spaces, non-ASCII or URL-significant characters
- **THEN** following its link opens the captured parent directory with the
  original filename as a literal filter

#### Scenario: Directory and structural parent
- **WHEN** a user opens an actual matched directory or a structural parent node
- **THEN** the destination preserves the existing directory/filter semantics

#### Scenario: Search draft changes after results
- **WHEN** the user changes search input without submitting another search
- **THEN** existing result links continue using the previous executed criteria

### Requirement: Search new-tab actions preserve source state

Advanced search SHALL provide an accessible explicit new-tab link next to result
names. Middle-click, modified-click and explicit new-tab navigation SHALL retain
the source URL, search dialog, checked paths and expanded nodes. Ordinary clicks
SHALL retain the existing navigation and dialog-close behavior. Name links,
expansion controls and checkboxes SHALL be independently operable, and structural
parents SHALL NOT become real batch targets merely because they have links.

#### Scenario: New-tab icon and result selection
- **WHEN** a user opens a checked search result in another tab
- **THEN** the source dialog and checked paths remain intact
- **AND** the new tab reaches the same destination as ordinary navigation

#### Scenario: Expansion and batch actions remain independent
- **WHEN** a user toggles a directory or checkbox in the result tree
- **THEN** only the corresponding expansion or selection action occurs
- **AND** no navigation is triggered

### Requirement: Button appearance does not change link semantics

Links displayed with button, badge or sidebar styling SHALL remain links with
usable destinations and keyboard access. Explicit new-tab links SHALL isolate
the opened window from its opener. Action-only controls SHALL NOT gain navigable
destinations or perform an action when a neighboring link is opened.

#### Scenario: Styled fixed-destination control
- **WHEN** a user opens a styled navigation control in a new tab
- **THEN** the browser follows its link without invoking a parent action handler
