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
- [x] server management page
  - [x] overview page: console, online players (same as bellow), cpu & memory usage (w/docker), disk space usage (w/du), warning for backup mod
  - [x] player listing (use log tracking and occasional sync using rcon. info queried from 25565 isn't reliable)
  - [x] compose file management page
  - [ ] file management page
    - [x] basic file management
    - [ ] restore file: for player files, restore when player isn't online; for other files, ask for server stop.
  - [ ] pack and download archive (warn about server stop)
- [ ] create new server page
- [ ] snapshot management page
- [x] super admmin page
  - [x] user management page

### backend
