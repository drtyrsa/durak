# Это pyDurak
Во-первых, это игра в карточного дурака, написанная на Питоне. Во-вторых, это инфраструктура, в которой можно проводить матчи между компьютерными программами, играющими в дурака (дальше я буду называть их движками, по аналогии с компьютерными шахматами). Сами движки могут быть написаны на любом языке.

Состоит все из нескольких компонентов:
  - **durak-gui** — визуальный интерфейс, в котором можно выбрать движок и сразиться с ним.
  - **durak-autoplay** — консольная утилита, позволяющая стравить между собой два движка. Результат выводится на экран. Сами игры могут писаться в лог.
  - **durak-logviewer** — визуальный просмотрщик логов игр.
  - **durak-dummy** — простенький движок для примера.

Подробная документация есть в папке `docs`. Ах да, правила. Обычный подкидной дурак, один на один. Каких-то особых правил типа «первый отбой — пять карт» нет.

## Это OpenSource
Я буду рад любым пул-реквестам, баг-репортам, форкам и критике. Вдвойне буду рад, если кто-то напишет свой движок, который всех обыграет (написать свой движок очень просто, ведь есть документация, прямо в папке `docs`). Распространяется все по [лицензии MIT](http://www.opensource.org/licenses/MIT).

На всякий случай мой емайл — [drtyrsa@yandex.ru](mailto:drtyrsa@yandex.ru).