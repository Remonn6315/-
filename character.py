from dataclasses import dataclass

@dataclass
class Character:
    name: str
    hp: int
    attack: int
    defense: int

    def __post_init__(self):
        # Validate that HP, attack, and defense are non-negative integers
        if self.hp < 0 or self.attack < 0 or self.defense < 0:
            raise ValueError("HP, attack, and defense must be non-negative values.")

    def take_damage(self, damage: int) -> None:
        """
        キャラクターにダメージを与えるメソッド。

        :param damage: 与えられるダメージ量 (int)
        :raises TypeError: ダメージが整数でない場合
        """
        if not isinstance(damage, int):
            raise TypeError("Damage must be an integer.")
        
        self.hp = max(0, self.hp - damage)