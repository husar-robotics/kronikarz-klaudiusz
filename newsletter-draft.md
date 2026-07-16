## TL;DR

- Piesek Wojtka: w poniedziałek test RPi na robocie, a Jakub pisze do autora konstrukcji (z prośbą o licencję MIT i zaproszeniem na serwer).
- Nawigacja: lokalny Qwen podmieniony za Claude działa, ale myli kierunki i gubi cel; PR w drodze. Obok dyskusja o brakującym "systemie 3" do planowania przestrzennego.
- Lokomocja: z papieru RMA wyciągnięty elegancki regularyzator −‖a‖² (kara za odchylenie od home position) jako kandydat na nowy loss.
- Branding: piesek w stylistyce karbonu; pomysł na formowanie prawdziwego karbonu na wydruku 3D zamiast pełnej karbonowej konstrukcji.
- Na serwer dołączył Paweł, student AI z zacięciem audio.

## Discussions

**Plan dla pieska Wojtka.** Przegląd stanu prac: ROS i RT kernel na RPi ogarnia Jakub (test na robocie w poniedziałek), sim2real i jitter dalej w walce, a praca u podstaw lekko utknęła względem reszty. Kluczowa decyzja dnia: zamiast zgadywać parametry napędów, Jakub kontaktuje się bezpośrednio z autorem robota; przy okazji prośba o licencję MIT dla repo i pomysł zaproszenia autora na serwer. ([wątek](https://discord.com/channels/1521375012232101948/1524542467964141649/1525554381775175721), [decyzja](https://discord.com/channels/1521375012232101948/1524542467964141649/1525558103863460032))

**Nawigacja i "system 3".** Maciej podmienił Claude na lokalnego Qwena w stacku nawigacyjnym: działa, ale robot myli kierunki i gubi krzesło, którego szuka; PR z lokalnym backendem w drodze. Greg na bazie świeżych paperów opisał lukę w architekturze: system 1 to lokomocja, system 2 to sterowanie z kamerki, brakuje systemu 3 od analizy przestrzeni i planowania. Jakub spiął to ze swoim pomysłem "supervisora" nad stackiem ROS. ([demo](https://discord.com/channels/1521375012232101948/1524440202888740964/1525296787152437288), [system 3](https://discord.com/channels/1521375012232101948/1524440202888740964/1525481177048420413), [supervisor](https://discord.com/channels/1521375012232101948/1524440202888740964/1525557022081155272))

**Regularyzacja nagród w lokomocji.** Michał wyciągnął z papieru RMA składnik −‖a‖²: kara za wielkość akcji, która ściąga politykę do domyślnej konfiguracji stawów i ogranicza eksploity na skrajnych pozycjach. Marcin miał podobny składnik w ostatnim eksperymencie, bez jednoznacznego wyniku. Otwarte pytanie: czy dodać też ground impact loss, którego w naszym setupie brakuje. ([wątek](https://discord.com/channels/1521375012232101948/1524440173285478551/1525576534637809834))

**Karbonowy piesek.** Przemek pokazał wizualizacje pieska w karbonie; konsensus, że wygląda świetnie, ale pełny karbon odpada. Pomysł zastępczy: druk 3D plus wygładzenie i malowanie, a z prawdziwego karbonu tylko przyłbica i pokrywa grzbietu, formowane na wydrukowanym kopycie. W tle nierozstrzygnięty spór estetyczny: maszyna do zabijania czy sympatyczny piesek do roznoszenia piwka. ([wątek](https://discord.com/channels/1521375012232101948/1524371077470490644/1525265535221366879), [kopyto](https://discord.com/channels/1521375012232101948/1524371077470490644/1525455328794116136))

**MJX i kolizje meshy.** Przy okazji nawigacji wypłynęło ograniczenie "MJX cannot do mesh collisions"; pytanie, czy MuJoCo Warp je znosi, zostało otwarte. W dotychczasowych eksperymentach meshe były po prostu zastępowane bryłami. ([wątek](https://discord.com/channels/1521375012232101948/1524440202888740964/1525381241598119977))

## Papers & links

- [RMA: Rapid Motor Adaptation for Legged Robots](https://arxiv.org/abs/2107.04034) — Ashish Kumar, Zipeng Fu, Deepak Pathak, Jitendra Malik. Źródło regularyzatora −‖a‖² dyskutowanego w lokomocji. ([shared here](https://discord.com/channels/1521375012232101948/1524440173285478551/1525576534637809834))
- [FutureNav: Unified World-Action Modeling for Vision-and-Language Navigation](https://arxiv.org/pdf/2606.30367) — Lingfeng Zhang i in. Punkt wyjścia dyskusji o "systemie 3". ([shared here](https://discord.com/channels/1521375012232101948/1524440202888740964/1525480769907327088))
- [World Model for Robot Learning: A Comprehensive Survey](https://arxiv.org/abs/2605.00080v1) — Bohan Hou i in. Przegląd world models pod kątem planowania. ([shared here](https://discord.com/channels/1521375012232101948/1524440202888740964/1525494463034822876))
- [InternNav](https://github.com/InternRobotics/InternNav) — framework nawigacyjny; problem: pod spodem Isaac. ([shared here](https://discord.com/channels/1521375012232101948/1524440202888740964/1525457013625061456))
- [RUKA Hand v2](https://ruka-hand-v2.github.io/) — otwartoźródłowa dłoń robotyczna, do tematu OSS hardware. ([shared here](https://discord.com/channels/1521375012232101948/1521405821815095379/1525426261567078460))
- [Filmik o piesku](https://www.youtube.com/watch?v=HN-XBQRHXqM&t=1540s) — polecany opis konstrukcji robota. ([shared here](https://discord.com/channels/1521375012232101948/1521405821815095379/1525570068468203631))
- [Demo nawigacji z lokalnym Qwenem](https://drive.google.com/file/d/1_R9iN8ZnE5M4uDWMB5vlcmxeacyCAX3t/view?usp=sharing) — nagranie przejazdu. ([shared here](https://discord.com/channels/1521375012232101948/1524440202888740964/1525301740772134982))

## Learning corner

**Reward shaping i regularyzatory akcji.** W RL nagroda rzadko jest jednym celem: dokłada się składniki karzące niepożądane zachowania, np. −‖a‖² za duże akcje, żeby polityka nie eksploatowała skrajnych pozycji stawów. Sztuką jest balans, bo każdy składnik ciągnie politykę w inną stronę. Więcej: [Spinning Up — intro do RL](https://spinningup.openai.com/en/latest/spinningup/rl_intro.html).

**Kolizje meshy w symulacji.** Silniki fizyki liczą kolizje najszybciej na prostych bryłach (kapsuły, boxy), a dokładne siatki trójkątów (meshe) są drogie i niestabilne numerycznie, więc w treningu RL meshe często zastępuje się bryłami. Stąd ograniczenia typu "MJX cannot do mesh collisions". Więcej: [dokumentacja MuJoCo](https://mujoco.readthedocs.io/en/stable/computation/index.html).

**Domain randomization.** Technika zmniejszania luki sim2real: parametry symulacji (tarcie, masy, opóźnienia) losuje się w treningu, żeby polityka była odporna na to, że rzeczywistość różni się od symulatora. Wspomniana dziś "randomizacja latencji ukradziona z Isaaca" to dokładnie ten mechanizm. Więcej: [Domain Randomization — Lilian Weng](https://lilianweng.github.io/posts/2019-05-05-domain-randomization/).

**Formowanie karbonu na kopycie.** Elementy z włókna węglowego kształtuje się na formie (kopycie), na której układa się i utwardza tkaninę z żywicą. Wydrukowanie kopyta w 3D to tani sposób na małoseryjne części, np. przyłbicę pieska. Więcej: [Carbon-fiber-reinforced polymer](https://en.wikipedia.org/wiki/Carbon-fiber-reinforced_polymers).
