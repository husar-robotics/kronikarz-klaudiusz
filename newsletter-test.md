## TL;DR

- Trwa praca nad lokomocją bez zadanego gaitu; polityka uczy się skradania i wyżej podnosi nogi, ale jest mniej stabilna.
- Michał podrzucił podejście "constraints as terminations" do balansowania rosnącej liczby nagród.
- W #si-high-level pojawiły się dwa nowe papery z arXiv.

## Discussions

Dyskusja o balansowaniu nagród w treningu RL: podział na cele optymalizacyjne i ograniczenia typu "good enough", z probabilistycznym ubijaniem epizodów naruszających constrainty. ([wątek](https://discord.com/channels/1521375012232101948/1524440173285478551/1525107028056473731))

## Papers & links

- [RMA: Rapid Motor Adaptation for Legged Robots](https://arxiv.org/abs/2107.04034) — źródło pomysłu na karę za odchylenie od pozycji domowej. ([shared here](https://discord.com/channels/1521375012232101948/1524440173285478551/1525576534637809834))
- [Constraints as Terminations](https://constraints-as-terminations.github.io/) — propozycja rozwiązania problemu balansowania nagród. ([shared here](https://discord.com/channels/1521375012232101948/1524440173285478551/1525107028056473731))
- [Dead link test](https://this-domain-does-not-exist-kx9z.example/paper) — celowo martwy link do testu walidatora.

## Learning corner

**Quasi-direct drive (QDD)**: napęd łączący silnik o dużym momencie z niską przekładnią, co daje dobrą kontrolę siły bez delikatnych przekładni harmonicznych. Punkt wyjścia: [MIT Mini Cheetah paper](https://arxiv.org/abs/1909.06586).

**Reward shaping**: dobór składników nagrody w RL tak, by polityka uczyła się pożądanych zachowań bez eksploitów. Dobre wprowadzenie: [Spinning Up — RL intro](https://spinningup.openai.com/en/latest/spinningup/rl_intro.html).
