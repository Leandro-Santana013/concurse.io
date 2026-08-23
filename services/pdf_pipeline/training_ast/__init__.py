"""
concurse.io — Motor AST para Expressões Regulares e Treinamento Genético
=======================================================================
Manipula expressões regulares através de Árvore Sintática Abstrata (AST),
garantindo 100% de validade sintática por construção em todas as mutações genéticas.
"""

from .ast_regex import (
    ASTNode,
    Literal,
    CharClass,
    Anchor,
    Quantifier,
    Group,
    Alternative,
    parse_regex_to_ast,
    mutate_ast,
    crossover_ast,
    ast_to_compiled_regex,
)

__all__ = [
    "ASTNode",
    "Literal",
    "CharClass",
    "Anchor",
    "Quantifier",
    "Group",
    "Alternative",
    "parse_regex_to_ast",
    "mutate_ast",
    "crossover_ast",
    "ast_to_compiled_regex",
]
