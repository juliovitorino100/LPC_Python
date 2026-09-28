"""Exceções do domínio.

O Java lançava ``java.lang.Exception`` genérica. Em Python, criamos uma
hierarquia própria para permitir ``except`` específico sem capturar tudo.
"""


class LpcError(Exception):
    """Base para erros do simulador LPC."""


class InvalidErrorPositionError(LpcError, ValueError):
    """Posição de erro fora do intervalo 0..47.

    Equivale a ``throw new Exception("Error position = " + errorPosition)`` em
    ``LpcWithErrror.setError``. A mensagem foi mantida idêntica.

    Diferença consciente: no Java, posições **negativas** caíam no primeiro
    ``if (errorPosition < 16)`` e estouravam ``ArrayIndexOutOfBoundsException``.
    Em Python, índices negativos acessariam a lista "pelo fim" e alterariam um
    bit errado em silêncio, então negativos também levantam esta exceção.
    """

    def __init__(self, position: int) -> None:
        super().__init__(f"Error position = {position}")
        self.position = position
