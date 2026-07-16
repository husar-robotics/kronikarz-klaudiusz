## Commits

- [fef411f](https://github.com/husar-robotics/shrek-dog/commit/fef411f29247d5cc8c17b35ef5e3d749cae90bb2) Merge pull request #23 from husar-robotics/claude/wcss-setup-verify-75e7c1 — marcinwysocki
- [7fb04ee](https://github.com/husar-robotics/shrek-dog/commit/7fb04eee5b2ca2b5dd264c6e25f605ec603c6708) docs(skills): add Greg's login-node watchdog to wcss-hpc skill — marcinwysocki
- [2068bd6](https://github.com/husar-robotics/shrek-dog/commit/2068bd6f3c20437b0d64a008a743ded1a387a1f5) Merge pull request #22 from husar-robotics/codex/document-training-configurations — marcinwysocki
- [e01354f](https://github.com/husar-robotics/shrek-dog/commit/e01354fd6211bf36a2a29eb951687e19a7a0e167) docs: add agent training configuration reference — marcinwysocki
- [1c5d938](https://github.com/husar-robotics/shrek-dog/commit/1c5d9388bb02073bda42e720311ba133ed334b89) Merge pull request #15 from husar-robotics/mwysocki/mjwarp-migration — marcinwysocki
- [8e186e8](https://github.com/husar-robotics/shrek-dog/commit/8e186e86d67e6e3faeac7258b72fae4b0eb29211) test: pin yaml defaults to code defaults; cover combined and vmapped paths — marcinwysocki
- [37a9ea1](https://github.com/husar-robotics/shrek-dog/commit/37a9ea11bbbfa4f4fd94ba924effc0411799f902) fix(train): error when dr fields are enabled but domain_rand=false — marcinwysocki
- [bd33599](https://github.com/husar-robotics/shrek-dog/commit/bd33599850eacbb1c055a1a91cb5add25a421273) fix(env): validate latency range; correct per-episode wording; encoder yaml block — marcinwysocki
- [e7d0280](https://github.com/husar-robotics/shrek-dog/commit/e7d0280d6cf92f204ab48ba2408f4286025d3703) fix(dr): give foot geoms contact priority so per-foot friction reaches the contact — marcinwysocki
- [e8c440b](https://github.com/husar-robotics/shrek-dog/commit/e8c440b1016e10d872f2ef43e5e76e68a565a798) docs: tighten verbose comments to plain prose (no behavior change) — marcinwysocki
- [5c7bfad](https://github.com/husar-robotics/shrek-dog/commit/5c7bfad61151197d6680b37754dfb685ce9be7cf) feat(env): encoder-zero offset DR (obs+ctrl shift; four-bar anchor untouched) — marcinwysocki
- [f23769c](https://github.com/husar-robotics/shrek-dog/commit/f23769c3d7d1a1fa221ab318c8b0318b478713a6) feat(env): per-substep randomized control latency — marcinwysocki
- [d6ac202](https://github.com/husar-robotics/shrek-dog/commit/d6ac20224136d67ef1e043174130e0472df5f5ce) feat(dr): expand DR taxonomy — CoM offset, per-joint gains, dof, per-foot friction — marcinwysocki

## Merged PRs

- [#23](https://github.com/husar-robotics/shrek-dog/pull/23) Add Greg's WCSS login-node watchdog to the wcss-hpc skill — marcinwysocki
- [#22](https://github.com/husar-robotics/shrek-dog/pull/22) docs: add agent training configuration reference — marcinwysocki
- [#15](https://github.com/husar-robotics/shrek-dog/pull/15) feat(training): sim2real DR + randomized latency + encoder offset (stacked on warp backend) — marcinwysocki