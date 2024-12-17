# MC-ADMIN

Project for learning Vue3, Nuxt and Tailwind

WIP

## TODOs

### fronend

- [x] login page: password and bot login
- [ ] dashboard page
  - [x] system cpu, ram and disk usage.
  - [x] total player count (player count queried from mc-health)
  - [ ] component check (docker, restic)
  - [x] listing, running state (down, created, running, running(paused)), player count
  - [x] restart, start, stop, down, up
- [ ] server management page
  - [ ] overview: console, online players (same as bellow), cpu & memory usage (w/docker), disk space usage (w/du), warning for backup mod
  - [ ] player listing (use log tracking and occasional sync using rcon. info queried from 25565 isn't reliable)
  - [ ] compose file management
  - [ ] file management
    - [ ] restore file: for player files, restore when player isn't online; for other files, ask for server stop.
  - [ ] whitelist management
  - [ ] blacklist management
  - [ ] pack and download archive (warn about server stop)
- [ ] create new server page
- [ ] backup management

### backend
