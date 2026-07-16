## Commits

- [1fdb74f](https://github.com/husar-robotics/shrek-dog/commit/1fdb74f5082387ac79ac499f879e052b5583914f) chore: drop 5_fbb_ros2_deploy — superseded by piesek_ws — mipo57
- [108115e](https://github.com/husar-robotics/shrek-dog/commit/108115e784d83d85074bf81cc606c6a92428b60a) feat(piesek): warn when the MuJoCo sim falls behind real time — mipo57
- [3c8beb2](https://github.com/husar-robotics/shrek-dog/commit/3c8beb2239911b8d159bba7d7222cec2bfcba0f9) feat(piesek): action_ema anti-vibration filter, live-tunable — mipo57
- [b6d431f](https://github.com/husar-robotics/shrek-dog/commit/b6d431f482da8fa71f13ef9e91d4f27373f79ea1) Native (non-docker) deploy via RoboStack + hold-to-move WASD teleop (#9) — Bukareszt
- [de386e9](https://github.com/husar-robotics/shrek-dog/commit/de386e9230bc93d769b13edc1003024825430e5e) fix(piesek): NaN input guard vs no-IMU policies — mipo57
- [09943c5](https://github.com/husar-robotics/shrek-dog/commit/09943c57b20f6eb41f3d6bc40c086abcd8c24b7b) Merge origin/main (working strafing robot) — keep robot-side fixes — mipo57
- [06266fc](https://github.com/husar-robotics/shrek-dog/commit/06266fc34f99d3dda6ee3ec7e0f610b04d3da3c6) chore(piesek): disable flaky BMI160 IMU on the real robot — mipo57
- [84b58ec](https://github.com/husar-robotics/shrek-dog/commit/84b58ecca072ea7496f3a32503c104113ae374ff) feat(piesek): xbox controller teleop — mipo57
- [ec0f99e](https://github.com/husar-robotics/shrek-dog/commit/ec0f99ed638506cd075a315579071ccd5df34e30) feat(piesek): deploy fbb_loco_v8 — 48-D no-IMU policy runtime — mipo57
- [0f905f6](https://github.com/husar-robotics/shrek-dog/commit/0f905f6317d8cf8f6d445d4dd4711603923983c4) working strafing robot — jakuc
- [b40132a](https://github.com/husar-robotics/shrek-dog/commit/b40132ad40611b9fd83237c682b7d1c9c9e43dd0) Merge pull request #8 from husar-robotics/mp/fbb-getup-run-jump — mipo57
- [40fc09d](https://github.com/husar-robotics/shrek-dog/commit/40fc09d11f446c4408daeefa0169af588167d5fd) feat(piesek): vendor piesek_ws ROS 2 workspace from robot — mipo57
- [374aaa5](https://github.com/husar-robotics/shrek-dog/commit/374aaa5377f3f2b31ec0ed64ed15d66b27b9bce4) docs(fbb-rl): overnight locomotion iteration log v1-v9 — winner fbb_loco_v8 — mipo57
- [1cf399d](https://github.com/husar-robotics/shrek-dog/commit/1cf399dc4f220298fad923ae5b908f67e4ace450) feat(fbb-rl): v8 — speed/precision frontier midpoint (slip -0.35, tracking 2.5) — mipo57
- [6bf9330](https://github.com/husar-robotics/shrek-dog/commit/6bf9330a7f391b593801b2f93cfddc01fdb9c1a5) feat(fbb-rl): v7 — slip penalty x2, height_tracking 2.5 (v6 residuals) — mipo57
- [5eb8700](https://github.com/husar-robotics/shrek-dog/commit/5eb870084d39383e611034e099b864d7681be4e0) fix(fbb-rl): battery stand metric — hold windows only; v6 preset — mipo57
- [a11bfa2](https://github.com/husar-robotics/shrek-dog/commit/a11bfa210101aead3b515fcbd9e863f08d8a4171) feat(fbb-rl): v5 — EMA action filter (structural tremble fix), anchor weight reverted — mipo57
- [d711ee3](https://github.com/husar-robotics/shrek-dog/commit/d711ee373c367625841437b79f6117bfcdeb5202) feat(fbb-rl): v4 — stand-quality focus; battery measures push-free — mipo57
- [6aa513d](https://github.com/husar-robotics/shrek-dog/commit/6aa513db2ff76d8e54d12e3f358839215a747f51) feat(fbb-rl): v3 — faster clock cap, stronger vel tracking, damped stand — mipo57

## Merged PRs

- [#9](https://github.com/husar-robotics/shrek-dog/pull/9) Native (non-docker) deploy via RoboStack + hold-to-move WASD teleop — Bukareszt
- [#8](https://github.com/husar-robotics/shrek-dog/pull/8) Mp/fbb getup run jump — mipo57