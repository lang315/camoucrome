# Windows build: environment guard

`out\<dir>\environment.x64` holds the PATH every compile and link runs under (`ninja -t msvc -e`).
`gn.bat` appends its own directory to PATH, so a regen through it changes every command line and
rebuilds the whole graph (about 25k steps, 3 h; 2026-11-20).

After a clean build, record the environment:

    python scripts\windows\check_env_x64.py out\Official --record

Before every build that follows a `gn gen`, check it:

    python scripts\windows\check_env_x64.py out\Official

Exit 1 names the variables that differ (PATH as a count of entries, never values). On a mismatch, run
`buildtools\win\gn.exe gen out\Official` directly under the recorded PATH (not `gn.bat`), then
check again. The record is `out\Official.envhash.json`, beside the out dir.
