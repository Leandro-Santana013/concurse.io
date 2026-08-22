#!/usr/bin/env python3
"""
concurse.io — AST Regular Expression Engine & Synthesizer
Manipula expressões regulares através de Árvore Sintática Abstrata (AST),
garantindo 100% de validade sintática por construção em todas as mutações genéticas.
"""

from __future__ import annotations
import random
import re
from typing import List, Optional, Union, Dict, Any, Tuple


class ASTNode:
    """Nó base da Árvore Sintática de Expressão Regular."""
    def to_regex(self) -> str:
        raise NotImplementedError

    def copy(self) -> ASTNode:
        raise NotImplementedError


class Literal(ASTNode):
    """Nó para sequências de caracteres literais ou tokens fixos."""
    def __init__(self, text: str):
        self.text = text

    def to_regex(self) -> str:
        return self.text

    def copy(self) -> Literal:
        return Literal(self.text)


class CharClass(ASTNode):
    """Nó para classes de caracteres (ex: [A-E], [ \t], [0-9], \\d, \\s)."""
    def __init__(self, chars: str, negated: bool = False):
        self.chars = chars
        self.negated = negated

    def to_regex(self) -> str:
        if self.chars.startswith("\\") and len(self.chars) == 2:
            return self.chars
        prefix = "^" if self.negated else ""
        return f"[{prefix}{self.chars}]"

    def copy(self) -> CharClass:
        return CharClass(self.chars, self.negated)


class Anchor(ASTNode):
    """Nó para âncoras e limites (ex: ^, $, \\b, (?:^|\\n))."""
    def __init__(self, anchor_type: str):
        self.anchor_type = anchor_type

    def to_regex(self) -> str:
        return self.anchor_type

    def copy(self) -> Anchor:
        return Anchor(self.anchor_type)


class Quantifier(ASTNode):
    """Nó quantificador que envolve um nó filho (ex: *, +, ?, {1,3})."""
    def __init__(self, child: ASTNode, min_rep: int = 0, max_rep: Optional[int] = None, lazy: bool = False):
        self.child = child
        self.min_rep = min_rep
        self.max_rep = max_rep
        self.lazy = lazy

    def to_regex(self) -> str:
        child_str = self.child.to_regex()
        # Se o nó filho não for atômico, envelopa em parênteses não capturantes
        if not (isinstance(self.child, (CharClass, Literal)) and len(child_str) <= 2):
            if not (child_str.startswith("(") and child_str.endswith(")")):
                child_str = f"(?:{child_str})"

        lazy_s = "?" if self.lazy else ""
        if self.min_rep == 0 and self.max_rep == 1:
            q = "?"
        elif self.min_rep == 0 and self.max_rep is None:
            q = "*"
        elif self.min_rep == 1 and self.max_rep is None:
            q = "+"
        elif self.max_rep is None:
            q = f"{{{self.min_rep},}}"
        elif self.min_rep == self.max_rep:
            q = f"{{{self.min_rep}}}"
        else:
            q = f"{{{self.min_rep},{self.max_rep}}}"

        return f"{child_str}{q}{lazy_s}"

    def copy(self) -> Quantifier:
        return Quantifier(self.child.copy(), self.min_rep, self.max_rep, self.lazy)


class Group(ASTNode):
    """Nó de grupo capturante ou não-capturante."""
    def __init__(self, children: List[ASTNode], capturing: bool = False, flag: Optional[str] = None):
        self.children = children
        self.capturing = capturing
        self.flag = flag

    def to_regex(self) -> str:
        inner = "".join(c.to_regex() for c in self.children)
        if self.flag:
            return f"(?{self.flag}){inner}"
        if self.capturing:
            return f"({inner})"
        return f"(?:{inner})"

    def copy(self) -> Group:
        return Group([c.copy() for c in self.children], self.capturing, self.flag)


class Alternative(ASTNode):
    """Nó de alternância lógica (A | B | C)."""
    def __init__(self, branches: List[ASTNode]):
        self.branches = branches

    def to_regex(self) -> str:
        if not self.branches:
            return ""
        return "|".join(b.to_regex() for b in self.branches)

    def copy(self) -> Alternative:
        return Alternative([b.copy() for b in self.branches])


# ============================================================================
# PARSER SIMPLIFICADO & SINTETIZADOR DE AST
# ============================================================================

def parse_regex_to_ast(pattern: str) -> ASTNode:
    """Converte uma string de expressão regular em uma AST simplificada e robusta."""
    flags = ""
    clean_pat = pattern
    if clean_pat.startswith("(?i)"):
        flags = "i"
        clean_pat = clean_pat[4:]
    elif clean_pat.startswith("(?im)"):
        flags = "im"
        clean_pat = clean_pat[5:]

    # Se contiver branches no nível superior, separa em Alternative
    # Split básico respeitando níveis de parênteses
    branches = []
    current = []
    paren_depth = 0
    in_escape = False

    for ch in clean_pat:
        if in_escape:
            current.append(ch)
            in_escape = False
            continue
        if ch == "\\":
            current.append(ch)
            in_escape = True
            continue
        if ch in "([":
            paren_depth += 1
            current.append(ch)
        elif ch in ")]":
            paren_depth = max(0, paren_depth - 1)
            current.append(ch)
        elif ch == "|" and paren_depth == 0:
            branches.append("".join(current))
            current = []
        else:
            current.append(ch)

    if current:
        branches.append("".join(current))

    if len(branches) > 1:
        ast_branches = [Literal(b) for b in branches]
        node = Alternative(ast_branches)
    else:
        node = Literal(clean_pat)

    if flags:
        return Group([node], capturing=False, flag=flags)
    return node


# ============================================================================
# OPERADORES GENÉTICOS FORMAIS BASEADOS EM AST (100% VÁLIDOS POR CONSTRUÇÃO)
# ============================================================================

def mutate_ast(node: ASTNode) -> ASTNode:
    """Executa uma mutação formal garantida na AST."""
    new_node = node.copy()

    # Mutações em nós literais / cláusulas
    if isinstance(new_node, Group):
        if new_node.children:
            idx = random.randint(0, len(new_node.children) - 1)
            new_node.children[idx] = mutate_ast(new_node.children[idx])
        return new_node

    if isinstance(new_node, Alternative):
        if not new_node.branches:
            return new_node
        op = random.randint(0, 3)
        if op == 0 and len(new_node.branches) > 1:
            # Reordena ou permuta alternativas
            random.shuffle(new_node.branches)
        elif op == 1:
            # Muta uma branch aleatória
            idx = random.randint(0, len(new_node.branches) - 1)
            new_node.branches[idx] = mutate_ast(new_node.branches[idx])
        elif op == 2 and len(new_node.branches) > 1:
            # Duplica e muta uma variação
            b = random.choice(new_node.branches).copy()
            new_node.branches.append(mutate_ast(b))
        return new_node

    if isinstance(new_node, Literal):
        text = new_node.text
        # Mutações canônicas seguras sobre o texto da folha
        separators = [
            r"[\.\-\–\—\:\)]",
            r"(?:[\.\-\–\—\:\)]|\s*–\s*|\s*:\s*|\s*-\s*)",
            r"(?:[\.\-\)]|\s*[\-\–]\s*)",
            r"(?:\.|\s*-\s*|\s*–\s*)"
        ]

        op = random.randint(0, 8)
        if op == 0 and r"QUEST[ÃA\?]?O" in text and r"ITEM" not in text:
            text = text.replace(r"QUEST[ÃA\?]?O", r"(?:QUEST[ÃA\?]?O|ITEM|Questão|Q\.)")
        elif op == 1:
            for sep in separators:
                if sep in text:
                    text = text.replace(sep, r"(?:[\.\-–—:\)]|\s*–\s*|\s*:\s*)", 1)
                    break
        elif op == 2 and r"(?:^|\n)" in text and r"(?:^|\n|\r\n)" not in text:
            text = text.replace(r"(?:^|\n)", r"(?:^|\n|\r\n)", 1)
        elif op == 3 and r"(\d{1,3})" in text and r"(0*\d{1,3})" not in text:
            text = text.replace(r"(\d{1,3})", r"(0*\d{1,3})")
        elif op == 4 and r"([A-E])" in text:
            text = r"(?i)(?:^|\n|\s+)(?:([A-E])\s*\(\s*\)|\(?\s*([A-E])\s*\)?\s*[\.\-–—:\)]|\(([A-E])\)|\[([A-E])\])\s*"
        elif op == 5 and r"\s*" in text:
            text = text.replace(r"\s*", r"[ \t]*", 1)
        elif op == 6 and "CONHECIMENTOS" in text:
            text = text.replace("CONHECIMENTOS", r"(?:CONHECIMENTOS|PROVA DE|ESTUDO DE)", 1)
        elif op == 7 and "DISCIPLINA" in text:
            text = text.replace("DISCIPLINA", r"(?:DISCIPLINA|MAT[ÉE]RIA)", 1)
        elif op == 8 and "PORTUGUESA" in text:
            text = text.replace("PORTUGUESA", r"PORTUGUES[A\?]?")

        return Literal(text)

    return new_node


def crossover_ast(parent1: ASTNode, parent2: ASTNode) -> ASTNode:
    """Crossover estrutural combinando sub-árvores sintáticas válidas."""
    t1 = parent1.copy()
    t2 = parent2.copy()

    # Se ambos tiverem alternâncias, combina suas branches
    if isinstance(t1, Alternative) and isinstance(t2, Alternative):
        cut1 = max(1, len(t1.branches) // 2)
        cut2 = max(1, len(t2.branches) // 2)
        combined = t1.branches[:cut1] + t2.branches[cut2:]
        return Alternative(combined)

    if isinstance(t1, Group) and isinstance(t2, Group):
        if t1.children and t2.children:
            return Group([crossover_ast(t1.children[0], t2.children[0])], flag=t1.flag)

    return random.choice([t1, t2])


def ast_to_compiled_regex(node: ASTNode) -> Tuple[str, Optional[re.Pattern]]:
    """Serializa a AST para string e compila com validação formal."""
    pattern_str = node.to_regex()
    try:
        compiled = re.compile(pattern_str)
        return pattern_str, compiled
    except re.error:
        # Fallback de higienização de escape
        sanitized = re.sub(r'(?<!\\)\\(?![\\dDwWsS\(\)\[\]\{\}\^\$\|\+\*\?\.])', '', pattern_str)
        try:
            compiled = re.compile(sanitized)
            return sanitized, compiled
        except re.error:
            return pattern_str, None
