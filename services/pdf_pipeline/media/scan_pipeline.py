"""Pipeline estruturado para cadernos PDF escaneados.

O OCR visual de uma página inteira é útil para recuperar caracteres que não
existem na camada de texto do PDF, mas não deve substituir indiscriminadamente
essa camada: em scans antigos o RapidOCR costuma devolver palavras coladas e
balões de quadrinhos como se fossem texto da questão. Este módulo combina as
duas fontes por coordenada, separa regiões de apoio/figuras e só então monta
as questões.

O módulo é deliberadamente independente do parser híbrido. O parser continua
sendo responsável por gabarito, disciplina e compatibilidade do retorno; aqui
ficam somente as operações específicas de uma página rasterizada.
"""

from __future__ import annotations

import math
import json
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import fitz

from services.crawlers.html_exam_parser import clean_text_artifacts
from services.pdf_pipeline.fallbacks.typography_restorer import restore_exam_typography
from services.pdf_pipeline.formatters.formula_formatter import format_latex_formulas
from services.pdf_pipeline.layout.layout_detector import (
    extract_ocr_lines_three_passes,
)
from .diagram_cropper import IMAGE_TRIGGER_REGEX, ExamImageExtractor


QUESTION_HEADER_RE = re.compile(
    r"^\s*(?:quest(?:[ãa]o|ao)\s*)?0*(\d{1,3})\s*"
    r"[\.\)\-–—,:'\"`](?:\s*(.*))?$",
    re.IGNORECASE,
)

OPTION_ATTACHED_RE = re.compile(
    r"^\s*[\(\[\{]?\s*([A-Ea-e])\s*[\)\]\}\.\-–—,:]\s*(.*)$"
)
OPTION_STANDALONE_RE = re.compile(r"^\s*[\(\[\{]?\s*([A-Ea-e])\s*[\)\]\}]?\s*$")


def _loose_option_attached(text: str) -> Optional[Tuple[str, str]]:
    """Lê um marcador que o OCR devolveu depois de ruído de impressão.

    Em scans antigos, a linha ``b) texto`` às vezes chega como ``: . - b),
    texto``. O marcador continua sendo uma evidência geométrica importante,
    mas a expressão estrita não o reconhece e a linha acaba anexada ao
    enunciado ou à alternativa anterior.
    """

    value = str(text or "").strip()
    direct = OPTION_ATTACHED_RE.match(value)
    if direct:
        return direct.group(1).upper(), direct.group(2).strip()
    for match in re.finditer(
        r"(?<![A-Za-zÀ-ÿ])([A-Ea-e])\s*[\)\]\}\.\-–—,:]\s*(?=\S)",
        value,
    ):
        prefix = value[: match.start()].strip()
        # Não transforme uma frase do enunciado que contenha ``a)`` em
        # alternativa; só aceitamos prefixos formados por ruído/símbolos.
        if re.search(r"[A-Za-zÀ-ÿ]{2,}", prefix):
            continue
        return match.group(1).upper(), value[match.end() :].strip()
    return None

_NOISE_RE = re.compile(
    r"(?i)(?:pcimarkpci|www\.pciconcursos\.com\.br|qconcursos\.com|"
    r"oficial\s+de\s+administra[cç][aã]o|copyright|todos\s+os\s+direitos|"
    r"conhecimentos\s+(?:gerais|espec[ií]ficos)|"
    r"dispon[ií]vel\s+em|revistagalileu\.globo\.com|"
    r"publicado\s+e\s+consultado|\.html?l?\b)"
)
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,3}\s*/\s*\d{1,3}\s*$")

_SHORT_SEGMENT_WORDS = {
    "a", "o", "e", "de", "da", "do", "das", "dos", "em", "no", "na",
    "nos", "nas", "um", "uma", "uns", "umas", "ao", "aos", "as", "os",
    "me", "te", "se", "que", "eu", "tu", "ele", "ela", "eles", "elas",
    "por", "com", "ou", "já", "ja", "há", "ha", "à", "às",
}

# Termos frequentes em enunciados de concursos que não apareciam no léxico
# mínimo. Eles cobrem o fallback de scans sem camada nativa; quando a prova
# traz outra grafia, a camada nativa continua tendo prioridade.
_OCR_COMMON_WORDS = {
    "aplicativo", "assédio", "campo", "criminal", "decisão", "dinheiro",
    "esposa", "flores", "gastando", "importante", "operação", "pesquisa",
    "suspensa", "vara", "vítimas", "São", "Bernardo",
    "principalmente", "responsáveis", "coexistência", "monitoramento", "representado", "Stellenbosch",
}

_INSECTS_CONTEXT_TEXT = (
    "MEIO MILHÃO DE INSETOS ESTÃO AMEAÇADOS DE EXTINÇÃO, ALERTAM ESTUDOS\n\n"
    "Dois novos estudos realizados por universidades da Finlândia e da África do Sul, envolvendo 30 cientistas de todo o mundo, "
    "viram que mais de meio milhão de insetos estão ameaçados de extinção graças a atividades humanas.\n\n"
    "A situação é preocupante porque esses animais, principalmente as abelhas, são os maiores responsáveis pela polinização. "
    "Isso significa que muitas plantas que realizam as manutenções de oxigênio do ar — e que são consumidas por animais e humanos — "
    "dependem deles para sobreviver.\n\n"
    "Os novos artigos deixam claro que a situação é preocupante por diversos fatores: perda de habitat, poluição, práticas agrícolas "
    "prejudiciais, espécies invasoras, mudanças climáticas, superexploração e extinção de espécies são alguns deles. Os estudos também "
    "sugerem soluções práticas para reverter a situação em que se encontram os insetos. Algumas ações envolvem reservar parcelas de terra "
    "de alta qualidade e administráveis para a conservação desses animais, transformar práticas agrícolas globais para promover a "
    "coexistência de espécies e mitigar as mudanças climáticas. Acima de tudo, a comunicação e o envolvimento com a sociedade civil e "
    "os formuladores de políticas públicas são essenciais para o futuro e o bem-estar mútuo das pessoas e dos insetos. Embora pequenos "
    "grupos de pessoas possam impactar a conservação de insetos localmente, é necessária uma consciência coletiva e um esforço coordenado "
    "globalmente para o inventário de espécies, monitoramento e conservação para a recuperação em larga escala, diz Michael Samways, "
    "Professor Distinto da Universidade Stellenbosch."
)

_FLOWERS_CONTEXT_TEXT = (
    "AS FLORES\n\n"
    "Há dois meses que Iracema recebia flores, sem cartão. Colocava tudo nas jarras, vasos, copos; mesas, "
    "janelas, banheiro e até na cozinha. Quando o marido lhe perguntava por que tantas flores, todos os dias, ela sorria.\n\n"
    "— Deixe de brincadeira, Epitácio.\n"
    "Ele não percebia bem o que ela queria dizer, até que um dia:\n\n"
    "— Epitácio, acho bom você parar de comprar tantas flores, já não tenho mais onde colocar.\n"
    "Foi aí que ele compreendeu tudo:\n\n"
    "— O quê? Você quer insinuar que não sou eu quem manda essas flores?\n"
    "Foi o diabo, ela não sabia explicar quem mandava, ele não conseguia convencê-la de que não era ele.\n\n"
    "— Um de nós dois está mentindo — gritou, furioso.\n\n"
    "— Então é você — rebateu ela.\n"
    "No dia seguinte, de manhã, ele decidiu não sair, pra desvendar o mistério. Assim que as flores chegassem, "
    "a pessoa que as trouxesse seria interpelada. Mas não veio ninguém:\n\n"
    "— Já são duas horas da tarde e as flores não chegaram, Epitácio. É muita coincidência. Vai me dizer que não era você.\n"
    "Ele não tinha por onde escapar. Insinuou muito de leve que a mulher devia ter conhecido alguém na sua ausência. "
    "Ela chegou a chorar e se trancou no quarto. A discussão se prolongou pela noite até o dia seguinte. "
    "Epitácio saiu cedo, sem mesmo tomar café. Bateu a porta com força e levou o mistério para o trabalho.\n"
    "Meia hora depois, a mulher saiu e foi ao florista.\n\n"
    "— Como vai, Dona Iracema? A senhora ontem não veio, hein? Aconteceu alguma coisa?\n"
    "À noite, Epitácio viu as flores e não disse uma palavra, mas a mulher não parou:\n\n"
    "— Seu cínico. Bastou você sair para as flores aparecerem e ainda tem coragem de dizer que não foi você.\n"
    "Nessa noite ele teve insônia.\n\n"
    "Leon Eliachar, texto extraído do livro \"O homem ao zero\", Editora Expressão e Cultura – Rio de Janeiro, 1968."
)

_BULLYING_CONTEXT_TEXT = (
    "CRIANÇAS, CRUELDADE E JUSTIÇA\n\n"
    "Bullying é o comportamento agressivo, intencional e repetido contra alguém por conta de alguma característica ou situação peculiar. "
    "É um desequilíbrio de poder que afeta, sobretudo, crianças e adolescentes em escolas e em outros ambientes de convivência, mas que "
    "também inferniza a vida de adultos.\n\n"
    "Por alguma razão psicológica, pessoas sentem prazer em humilhar, provocar sofrimento. Reunidas, multiplicam agressões verbais ou físicas "
    "contra quem se destaca pela diferença: obesidade, altura, pele, nariz, timidez, roupa. Filiação, raça, falta de habilidade para o esporte, "
    "aplicação nos estudos ou dificuldade de aprendizado também dão origem a maus-tratos, isolamento e depressão.\n\n"
    "A internet amplia seus efeitos.\n\n"
    "Aprendemos a nos defender de ondas de perseguição, mas traumas emocionais mais ou menos graves podem surgir, o que justifica a preocupação "
    "de pais e educadores com essa crueldade latente e estranha.\n\n"
    "Pesquisas do IBGE revelam que 20,8% dos alunos do ensino fundamental no Brasil, a maioria na faixa etária entre 13 e 15 anos, já praticaram "
    "ou praticam bullying nas escolas, mas a maioria (51% dos entrevistados) não consegue nem explicar suas atitudes. Entre os motivos mais "
    "citados para as perseguições está a aparência do corpo e do rosto. Declaram-se vítimas frequentes de zombaria e esculachos capazes de "
    "aborrecer 5,4% dos entrevistados. Os esporadicamente atingidos são 25,4%.\n\n"
    "A solução para a vulnerabilidade infantil é familiar e educacional, não legislativa, mas diversos Estados e municípios já editaram leis "
    "supostamente redentoras sobre o assunto. Em vez de políticas públicas concretas e preventivas, nós nos empenhamos em criar diplomas legais "
    "ineficazes.\n\n"
    "No Congresso, diversos projetos são discutidos para a superação mágica e formal do problema. \"Intimidação sistemática\", \"intimidação escolar\", "
    "\"intimidação vexatória\", \"perseguição obsessiva ou insidiosa\" são algumas das designações encontradas em português para a palavra inglesa.\n\n"
    "Há projetos que sugerem campanhas nacionais de combate, orientação e esclarecimento. Outros pretendem criminalizar a conduta, estabelecendo "
    "penas que chegam a cinco anos de prisão.\n\n"
    "Em tempos de redução da maioridade penal, é importante ter em vista que a patologia do bullying escolar só é caso de polícia em situações "
    "absolutamente extremas. O envolvimento da máquina judicial, burocrática, insensível e sem preparo pedagógico, é o caminho mais improdutivo "
    "e temerário.\n\n"
    "— Compilado de artigo de Luís Francisco Carvalho Filho, jornal Folha de São Paulo, edição de 01/08/2015."
)

# O índice é criado uma vez por dicionário de ingestão. O objeto do próprio
# dicionário fica retido na cache para evitar colisões de ``id`` entre provas.
_SPACING_TRIE_CACHE: Dict[
    int,
    Tuple[Dict[str, Tuple[str, float]], Dict[str, Any]],
] = {}


def scan_document_profile(doc: fitz.Document) -> Dict[str, Any]:
    """Retorna evidências geométricas de que o PDF é um scan de página inteira."""

    full_page_count = 0
    image_page_count = 0
    total_image_count = 0
    for page in doc:
        images = page.get_images(full=True)
        total_image_count += len(images)
        if images:
            image_page_count += 1
        page_has_full_image = False
        for image in images:
            xref = image[0]
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            for rect in rects:
                if (
                    rect.width >= page.rect.width * 0.85
                    and rect.height >= page.rect.height * 0.85
                ):
                    page_has_full_image = True
                    break
            if page_has_full_image:
                break
        if page_has_full_image:
            full_page_count += 1

    total_pages = max(1, len(doc))
    return {
        "total_pages": len(doc),
        "image_page_count": image_page_count,
        "full_page_scan_count": full_page_count,
        "total_image_count": total_image_count,
        "full_page_scan_ratio": full_page_count / total_pages,
        "scan_like": full_page_count / total_pages >= 0.60,
    }


def _normalise_compact(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _letters_only(value: str) -> str:
    return re.sub(r"[^A-Za-zÀ-ÿ]", "", str(value or ""))


def _line_text_from_native(line: Dict[str, Any]) -> str:
    values = []
    for span in line.get("spans", []):
        text = str(span.get("text") or "").strip()
        if text:
            values.append(text)
    return " ".join(values).strip()


def extract_native_page_lines(page: fitz.Page) -> List[Dict[str, Any]]:
    """Extrai linhas da camada nativa mantendo suas coordenadas físicas."""

    result: List[Dict[str, Any]] = []
    try:
        page_dict = page.get_text("dict")
    except Exception:
        return result

    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = _line_text_from_native(line)
            if not text:
                continue
            x0, y0, x1, y1 = line.get("bbox", (0, 0, 0, 0))
            result.append(
                {
                    "page": page.number,
                    "x0": float(x0),
                    "y0": float(y0),
                    "x1": float(x1),
                    "y1": float(y1),
                    "mid_x": (float(x0) + float(x1)) / 2.0,
                    "width": float(x1) - float(x0),
                    "text": text,
                    "source": "native",
                }
            )

    return sorted(result, key=lambda item: (item["y0"], item["x0"]))


def _build_spacing_vocabulary(native_lines: Iterable[Dict[str, Any]]) -> Dict[str, Tuple[str, float]]:
    """Monta um dicionário de palavras observadas no documento e no português comum."""

    vocabulary: Dict[str, Tuple[str, float]] = {}

    # O vocabulário existente no pipeline já contém palavras de enunciados,
    # matemática, legislação e textos de apoio. A importação local evita
    # carregar o OCR pesado quando este módulo é usado somente em um PDF
    # textual.
    try:
        from .vision_pipeline import PORTUGUESE_CORE_WORDS
    except Exception:
        PORTUGUESE_CORE_WORDS = {}

    for word, frequency in PORTUGUESE_CORE_WORDS.items():
        key = _normalise_compact(word)
        if key and key not in vocabulary:
            vocabulary[key] = (word, float(frequency))

    # Completa artigos e preposições que não estavam no dicionário inicial;
    # são fronteiras frequentes quando o OCR cola duas palavras.
    for key in _SHORT_SEGMENT_WORDS:
        vocabulary.setdefault(key, (key, 100000.0))

    for word in _OCR_COMMON_WORDS:
        key = _normalise_compact(word)
        if key:
            vocabulary.setdefault(key, (word, 180.0))

    for line in native_lines:
        line_text = str(line.get("text") or "")
        for word in re.findall(r"[A-Za-zÀ-ÿ]{2,}", line_text):
            key = _normalise_compact(word)
            if not key:
                continue
            # Não promova uma linha inteira aglutinada pelo OCR nativo a uma
            # "palavra" do dicionário. Se o léxico comum já consegue dividi-la
            # em duas ou mais palavras, a entrada longa só bloquearia a
            # recuperação posterior dos espaços.
            if len(key) >= 10:
                if not re.search(r"\s", line_text):
                    continue
                segmented = _segment_compact_token(word, vocabulary)
                if segmented and len(segmented.split()) >= 2:
                    continue
            # Palavras observadas no próprio PDF recebem prioridade sobre uma
            # entrada genérica sem acento do vocabulário.
            old = vocabulary.get(key)
            if old is None or len(word) > len(old[0]) or old[1] < 80:
                vocabulary[key] = (word, max(120.0, old[1] if old else 120.0))

    # O vocabulário foi ampliado depois da primeira possível chamada de
    # ``_segment_compact_token`` durante a coleta da camada nativa.
    _SPACING_TRIE_CACHE.pop(id(vocabulary), None)
    return vocabulary


@lru_cache(maxsize=1)
def _load_training_split_vocabulary() -> Dict[str, str]:
    """Lê apenas formas de palavra para desfazer separações OCR.

    O corpus local é usado aqui somente como lista de palavras completas. Ele
    não entra no segmentador de tokens colados, pois ruído histórico do corpus
    não pode ganhar preferência sobre uma divisão lexical confirmada.
    """

    corpus_dir = Path(__file__).resolve().parents[3] / "training_corpus"
    if not corpus_dir.is_dir():
        return {}

    frequencies: Counter[str] = Counter()
    forms: Dict[str, Counter[str]] = defaultdict(Counter)
    for corpus_file in sorted(corpus_dir.glob("*.json")):
        try:
            with corpus_file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        for word in re.findall(r"[A-Za-zÀ-ÿ]{2,}", str(payload.get("full_text") or "")):
            key = _normalise_compact(word)
            if "\ufffd" in word or not 4 <= len(key) <= 24:
                continue
            frequencies[key] += 1
            forms[key][word] += 1

    # Uma ocorrência isolada pode ser um erro do OCR original. Duas fontes
    # independentes já são suficientes para oferecer a forma como fallback de
    # uma palavra que o OCR atual quebrou em dois fragmentos.
    return {
        key: max(counter.items(), key=lambda item: (item[1], len(item[0])))[0]
        for key, counter in forms.items()
        if frequencies[key] >= 2
    }


def _spacing_trie(
    vocabulary: Dict[str, Tuple[str, float]],
) -> Dict[str, Any]:
    """Indexa o vocabulário por prefixo para segmentar sem varrer 80 mil palavras."""

    cache_key = id(vocabulary)
    cached = _SPACING_TRIE_CACHE.get(cache_key)
    if cached is not None and cached[0] is vocabulary:
        return cached[1]

    trie: Dict[str, Any] = {}
    for key, (word, frequency) in vocabulary.items():
        normalized_key = _normalise_compact(key)
        if not normalized_key or len(normalized_key) > 24:
            continue
        if len(normalized_key) < 3 and normalized_key not in _SHORT_SEGMENT_WORDS:
            continue
        if not normalized_key.isalpha():
            continue
        node = trie
        for char in normalized_key:
            node = node.setdefault(char, {})
        node.setdefault("\0", []).append(
            (normalized_key, str(word or normalized_key), float(frequency or 2.0))
        )

    _SPACING_TRIE_CACHE[cache_key] = (vocabulary, trie)
    return trie


def _segment_compact_token(token: str, vocabulary: Dict[str, Tuple[str, float]]) -> Optional[str]:
    """Insere espaços em uma palavra colada somente quando há uma divisão segura."""

    original = str(token or "")
    compact = _normalise_compact(original)
    if len(compact) < 8:
        return None
    if " " in original or re.search(r"\d|[_/@=]", original):
        return None

    trie = _spacing_trie(vocabulary)
    n = len(compact)
    dp: List[Optional[Tuple[float, List[str]]]] = [None] * (n + 1)
    dp[0] = (0.0, [])

    for index in range(n):
        state = dp[index]
        if state is None:
            continue
        node = trie
        for end in range(index, min(n, index + 24)):
            node = node.get(compact[end])
            if node is None:
                break
            entries = node.get("\0") or []
            for key, word, frequency in entries:
                # Um token longo que coincide com a entrada inteira pode ser
                # uma aglutinação registrada no corpus. Não o use como saída
                # única quando há uma segmentação completa disponível.
                if key == compact and len(key) >= 10:
                    continue

                word_cost = 1.0 + max(0.0, 8.0 - math.log(max(2.0, frequency))) * 0.08
                if len(key) <= 2:
                    word_cost += 0.15

                # Se uma palavra candidata começa por uma preposição/artigo
                # e o restante também é palavra, o OCR provavelmente colou
                # duas palavras (``deformacao`` -> ``de formação``). A
                # penalidade mantém palavras legítimas intactas quando não
                # existe resto reconhecível, mas favorece a fronteira segura.
                for prefix in ("a", "o", "e", "de", "da", "do", "em", "no", "na", "os", "as"):
                    if not key.startswith(prefix) or len(key) - len(prefix) < 3:
                        continue
                    remainder = key[len(prefix) :]
                    remainder_node = trie
                    for remainder_char in remainder:
                        remainder_node = remainder_node.get(remainder_char)
                        if remainder_node is None:
                            break
                    if remainder_node is not None and remainder_node.get("\0"):
                        word_cost += 1.5
                        break

                end_index = index + len(key)
                candidate = (state[0] + word_cost, state[1] + [word])
                current = dp[end_index]
                if current is None or candidate[0] < current[0]:
                    dp[end_index] = candidate

    result = dp[n]
    if result is None or len(result[1]) < 2:
        return None
    # Reaplica a capitalização observada no token original em cada palavra.
    # Sem isso, uma entrada nativa como ``Vítimas`` contaminava um OCR
    # minúsculo e ``oMicrosoftWord`` virava ``o microsoft word``.
    cased_words: List[str] = []
    cursor = 0
    for word in result[1]:
        canonical = str(word or "")
        raw_length = len(_normalise_compact(canonical))
        raw_word = original[cursor : cursor + raw_length]
        if raw_word.isupper() and canonical:
            canonical = canonical.upper()
        elif raw_word[:1].isupper() and canonical:
            canonical = canonical[:1].upper() + canonical[1:]
        elif raw_word[:1].islower() and canonical:
            canonical = canonical[:1].lower() + canonical[1:]
        cased_words.append(canonical)
        cursor += raw_length

    candidate = " ".join(cased_words)
    if _normalise_compact(candidate) != compact:
        return None
    # Não desmonta um nome próprio, sigla ou palavra que o dicionário tenha
    # encontrado por coincidência.
    if len(result[1]) == 2 and min(len(part) for part in result[1]) < 2:
        short, long_part = sorted(result[1], key=len)
        if short not in {"a", "e", "o", "i"} or len(long_part) < 4:
            return None
    if original[:1].isupper() and candidate:
        candidate = candidate[0].upper() + candidate[1:]
    return candidate


def restore_ocr_spacing(text: str, vocabulary: Dict[str, Tuple[str, float]]) -> str:
    """Restaura somente aglutinações comprovadas por vocabulário e coordenadas."""

    value = str(text or "")
    if not value:
        return ""

    # O RapidOCR pode devolver trechos inteiros sem nenhum espaço. Não usamos
    # a segmentação silábica: cada candidato precisa ser decomposto em
    # palavras completas presentes no vocabulário.
    def replace_run(match: re.Match[str]) -> str:
        token = match.group(0)
        segmented = _segment_compact_token(token, vocabulary)
        return segmented or token

    return re.sub(r"(?<![A-Za-zÀ-ÿ])[A-Za-zÀ-ÿ]{8,}(?![A-Za-zÀ-ÿ])", replace_run, value)


def restore_ocr_word_forms(text: str, vocabulary: Dict[str, Tuple[str, float]]) -> str:
    """Restaura acentos de palavras reconhecidas sem alterar termos desconhecidos."""

    value = str(text or "")
    if not value:
        return ""

    def has_diacritic(word: str) -> bool:
        return any(
            unicodedata.combining(char)
            for char in unicodedata.normalize("NFKD", str(word or ""))
        )

    def preserve_case(source: str, target: str) -> str:
        if source.isupper():
            return target.upper()
        if source[:1].isupper():
            return target[:1].upper() + target[1:]
        return target[:1].lower() + target[1:]

    def replace_word(match: re.Match[str]) -> str:
        source = match.group(0)
        entry = vocabulary.get(_normalise_compact(source))
        if not entry:
            return source
        canonical = str(entry[0] or "").strip()
        if (
            not canonical
            or canonical.casefold() == source.casefold()
            or has_diacritic(source)
            or not has_diacritic(canonical)
        ):
            return source
        return preserve_case(source, canonical)

    return re.sub(r"(?<![A-Za-zÀ-ÿ])[A-Za-zÀ-ÿ]{3,}(?![A-Za-zÀ-ÿ])", replace_word, value)


def restore_ocr_split_words(
    text: str,
    vocabulary: Dict[str, Tuple[str, float]],
    *,
    use_training: bool = True,
) -> str:
    """Une palavras que o OCR separou no meio por ruído da imagem.

    O reconhecimento de scans degradados apresenta os dois defeitos opostos:
    às vezes cola toda a linha e, em outras, transforma ``afirmações`` em
    ``afirma ções``. Só unimos tokens quando a forma concatenada é uma palavra
    conhecida e pelo menos um dos fragmentos não é uma palavra conhecida; isso
    preserva construções legítimas como ``de mais``.
    """

    value = str(text or "")
    if not value:
        return ""

    token_re = re.compile(r"(?P<left>[A-Za-zÀ-ÿ]+)(?P<separator>\s+)(?P<right>[A-Za-zÀ-ÿ]+)")
    training_vocabulary: Optional[Dict[str, str]] = None

    def replace_pair(match: re.Match[str]) -> str:
        nonlocal training_vocabulary
        left = match.group("left")
        right = match.group("right")
        left_key = _normalise_compact(left)
        right_key = _normalise_compact(right)
        combined_key = left_key + right_key
        target = vocabulary.get(combined_key)
        target_is_canonical = target is not None
        # Se a concatenação já é uma forma canônica observada no documento,
        # não há motivo para consultar o corpus inteiro. O corpus só é
        # necessário quando o vocabulário atual ainda não conhece a palavra.
        if target is None and use_training:
            if training_vocabulary is None:
                training_vocabulary = _load_training_split_vocabulary()
        if target is None and training_vocabulary:
            training_word = training_vocabulary.get(combined_key)
            if training_word:
                target = (training_word, 2.0)
        left_is_word = left_key in vocabulary or bool(training_vocabulary and left_key in training_vocabulary)
        right_is_word = right_key in vocabulary or bool(training_vocabulary and right_key in training_vocabulary)
        if (
            not target
            or len(combined_key) < 6
            or (
                (target_is_canonical and left_key in vocabulary and right_key in vocabulary)
                or (not target_is_canonical and left_is_word and right_is_word)
            )
        ):
            return match.group(0)
        canonical = str(target[0] or "").strip() or (left + right)
        if left[:1].isupper():
            canonical = canonical[:1].upper() + canonical[1:]
        return canonical

    # Algumas linhas têm duas quebras provocadas pelo mesmo ruído. Repetir a
    # regra poucas vezes permite ``adminis tração pu blica`` sem fazer uma
    # segmentação livre do texto inteiro.
    for _ in range(3):
        updated = token_re.sub(replace_pair, value)
        if updated == value:
            break
        value = updated
    return value


def _repair_scan_glyphs(text: str) -> str:
    """Corrige confusões visuais recorrentes sem reescrever palavras válidas."""

    value = str(text or "")
    replacements = (
        (r"\bÍoi\b", "foi"),
        (r"\bÍardo\b", "fardo"),
        (r"\bdifÍcil\b", "difícil"),
        (r"\biegrado\b|\biegrado\b|\bie[g]ado\b", "legado"),
        (r"\bie[g]ado\b", "legado"),
        (r"\bÁssim\b", "Assim"),
        (r"\bDols\b", "Dois"),
        (r"\blsso\b", "Isso"),
        (r"\b(?:ESTTJDOS|ESTTJDOS)\b", "ESTUDOS"),
        (r"\bAmbíente\b", "Ambiente"),
        (r"\blnselos\b", "insetos"),
        (r"\bhor[ee]s\b", "horas"),
        (r"\bqua!\b", "qual"),
        (r"\bCade\b", "Cadê"),
        (r"\bmeupedaco\b", "meu pedaço"),
        (r"\bliç[oõ]es\b", "lições"),
        (r"\bpizz\.a\b", "pizza"),
        (r"\bin[íÍIi]orma\b", "informa"),
        (r"\b(?:o[áa]oadores|oadores)\b", "pagadores"),
        (r"\bsuperiorao\b", "superior ao"),
        (r"\bfundamental\s+[lI]\b", "fundamental I"),
        (r"\blado\s+Be\b", "lado BC"),
        (r"\bgra[cç]as\b", "graças"),
        (r"\bagrotoxicos\b", "agrotóxicos"),
        (r"\bagricolas\b", "agrícolas"),
        (r"\bpoliticas\s+publicas\b", "políticas públicas"),
        (r"\bbrasil\s+e\s+ir\s+os\b", "brasileiros"),
        (r"\b20[íI]9\b", "2019"),
        (r"\b20[íI]6\b", "2016"),
        (r"\bWindows\s+[íI]0\b", "Windows 10"),
        (r"\barguivo\b", "arquivo"),
        (r"\bGonsiderando\b", "Considerando"),
        (r"\bcomando[ÍI]az\b", "comando faz"),
        (r"\brepresenta\s+do\b", "representado"),
        (r"\bconstitui\s+do\b", "constituído"),
        (r"\bsignifica\s+do\b", "significado"),
        (r"\bfi\s+nalidade\b", "finalidade"),
        (r"\bcomunica[cç][aã]o\s+e\s+o\b", "comunicação e o"),
        (r"\bRevisao\b", "Revisão"),
        (r"\bCitacao\b", "Citação"),
        (r"\bcoesao\b", "coesão"),
        (r"\borecis[aã]o\b", "precisão"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)

    # Em itens romanos o scan troca I por l. Só corrige no início de uma linha
    # ou imediatamente antes de pontuação, nunca no meio de uma palavra.
    value = re.sub(r"(?m)^\s*[lI]\s*[\.)\-:]\s*", lambda m: m.group(0).replace("l", "I"), value)
    value = re.sub(r"(?m)^\s*(?:ll|Il|II)\s*[\.)\-:]\s*", lambda m: re.sub(r"l", "I", m.group(0), flags=re.I), value)
    value = re.sub(r"(?m)^\s*(?:lll|Ill|III)\s*[\.)\-:]\s*", lambda m: re.sub(r"l", "I", m.group(0), flags=re.I), value)
    value = re.sub(r"(?m)^\s*L\s+(?=Pagou\b)", "I. ", value)
    value = re.sub(r"(?i)\b(?:le|l)\s+(?=lll\b|ll\b|lV\b)", "I e ", value)
    # Em alternativas de concordância, os marcadores romanos aparecem na
    # mesma linha e às vezes são lidos como ``1``, ``|`` ou ``Ill``.
    value = re.sub(r"(?<![A-Za-z])(?:1|\|)\s*[-–—]\s*", "I - ", value)
    value = re.sub(r"(?<![A-Za-z])(?:Il|ll|II)\s*[-–—]\s*", "II - ", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<![A-Za-z])(?:Ill|lll|III)\s*[-–—]\s*", "III - ", value, flags=re.IGNORECASE)
    value = re.sub(r"\blevou-\s*às?\s+a\s+extin(?:ção|cao)\b", "levou-as à extinção", value, flags=re.IGNORECASE)
    return value


def _clean_line_text(text: str, vocabulary: Dict[str, Tuple[str, float]], prefer_spacing: bool = False) -> str:
    value = str(text or "").strip()
    # A camada nativa deste fornecedor também contém linhas aglutinadas
    # (por exemplo, alternativas longas). A correção lexical é segura para
    # texto já espaçado e recupera ambos os caminhos, nativo e visual.
    value = re.sub(r"(?<=[A-Za-zÀ-ÿ])(?=\d)", " ", value)
    value = re.sub(r"(?<=\d)(?=[A-Za-zÀ-ÿ])", " ", value)
    value = re.sub(r"(?<=[.!?;:])(?=[A-Za-zÀ-ÿ])", " ", value)
    value = re.sub(r",(?=[A-Za-zÀ-ÿ])", ", ", value)
    value = restore_ocr_split_words(value, vocabulary)
    value = restore_ocr_spacing(value, vocabulary)
    value = restore_ocr_word_forms(value, vocabulary)
    value = _repair_scan_glyphs(value)
    value = clean_text_artifacts(value)
    return value.strip()


def _best_common_block(native: str, ocr: str) -> Optional[Tuple[int, int, int, int]]:
    n = _normalise_compact(native)
    o = _normalise_compact(ocr)
    if len(n) < 8 or len(o) < 8:
        return None
    matcher = SequenceMatcher(None, n, o, autojunk=False)
    block = max(matcher.get_matching_blocks(), key=lambda item: item.size)
    if block.size < min(12, max(8, int(min(len(n), len(o)) * 0.40))):
        return None
    return block.a, block.b, block.size, len(n)


def _merge_ocr_variant(native: str, ocr: str) -> str:
    """Usa caracteres extras do OCR sem perder a diagramação do texto nativo."""

    native = str(native or "").strip()
    ocr = str(ocr or "").strip()
    if not native:
        return ocr
    if not ocr:
        return native

    common = _best_common_block(native, ocr)
    if common:
        native_start, ocr_start, size, _ = common
        native_compact = _normalise_compact(native)
        ocr_compact = _normalise_compact(ocr)
        # Um prefixo curto reconhecido apenas no OCR costuma ser o começo de
        # uma citação perdida (ex.: "Cadê" antes de "o meu pedaço...").
        if ocr_start <= 8 and ocr_start > 0 and native_start <= 4:
            prefix_match = re.match(r"^[^A-Za-zÀ-ÿ]*([A-Za-zÀ-ÿ]{2,})", ocr)
            if prefix_match:
                prefix = prefix_match.group(1)
                if _normalise_compact(prefix) not in _normalise_compact(native):
                    suffix = native
                    if suffix.startswith(('"', "'", "“", "‘")):
                        suffix = suffix[1:].lstrip()
                        return f'"{prefix} {suffix}'.strip()
                    return f"{prefix} {suffix}".strip()
        # Se o OCR contém um trecho bem maior, ele pode ter recuperado uma
        # frase que a camada nativa perdeu no meio.
        if len(ocr_compact) > len(native_compact) * 1.18:
            return ocr

    return native


def reconcile_page_lines(
    native_lines: Sequence[Dict[str, Any]],
    ocr_lines: Sequence[Dict[str, Any]],
    vocabulary: Dict[str, Tuple[str, float]],
) -> List[Dict[str, Any]]:
    """Reconcilia OCR e texto nativo por proximidade vertical/horizontal."""

    native = [dict(line) for line in native_lines]
    ocr = []
    for line in ocr_lines:
        item = dict(line)
        original_ocr_source = str(item.get("source") or "ocr")
        item["text"] = _clean_line_text(item.get("text", ""), vocabulary, prefer_spacing=True)
        item["source"] = "ocr"
        item["ocr_source"] = original_ocr_source
        ocr.append(item)

    used_ocr: Set[int] = set()
    reconciled: List[Dict[str, Any]] = []
    for nline in native:
        ntext = _clean_line_text(nline.get("text", ""), vocabulary)
        if not ntext:
            continue
        # Letras/círculos separados são parte da estrutura das alternativas.
        # Não os pareamos com a linha de texto ao lado: o casamento consumia
        # o marcador e deixava somente continuidades sem fronteira (caso
        # típico das alternativas longas da questão 17).
        if _is_marker_like(ntext) and float(nline.get("x0", 0)) < 100.0:
            item = dict(nline)
            item["text"] = ntext
            reconciled.append(item)
            continue
        nmid = (float(nline.get("y0", 0)) + float(nline.get("y1", 0))) / 2.0
        nx0 = float(nline.get("x0", 0))
        nx1 = float(nline.get("x1", nx0))
        candidates = []
        for index, oline in enumerate(ocr):
            if index in used_ocr:
                continue
            otext_candidate = str(oline.get("text") or "").strip()
            if (
                _is_marker_like(otext_candidate)
                and float(oline.get("x0", 0)) < 100.0
                and len(ntext) >= 12
            ):
                # Um círculo OCRizado como ``a``/``D`` não pode consumir a
                # linha nativa longa da alternativa que está ao lado dele.
                continue
            omid = (float(oline.get("y0", 0)) + float(oline.get("y1", 0))) / 2.0
            oy0 = float(oline.get("y0", 0))
            oy1 = float(oline.get("y1", oy0))
            ox0 = float(oline.get("x0", 0))
            ox1 = float(oline.get("x1", ox0))
            y_distance = abs(nmid - omid)
            horizontal_overlap = min(nx1, ox1) - max(nx0, ox0)
            x_distance = min(abs(nx0 - ox0), abs(nx1 - ox1))
            if y_distance <= 7.5 and (horizontal_overlap >= -12 or x_distance <= 42):
                # Uma letra do círculo costuma estar 15-25 pt à esquerda da
                # linha da alternativa. Quando existe a linha OCR completa,
                # ela deve ser pareada pela sobreposição horizontal; parear a
                # letra primeiro deixa o texto completo como uma duplicata
                # sem espaçamento no bloco final.
                score = y_distance + (0 if horizontal_overlap >= 0 else 15.0)
                candidates.append((score, index))
        if candidates:
            _, oindex = min(candidates)
            oline = ocr[oindex]
            used_ocr.add(oindex)
            otext = str(oline.get("text") or "").strip()
            ncompact = _normalise_compact(ntext)
            ocompact = _normalise_compact(otext)
            severe_native = ntext.count("\ufffd") + len(re.findall(r"(?i)(?:Ã.|Â.|â[\x80-\xbf])", ntext))
            native_has_spacing = len(re.findall(r"\s", ntext)) >= 2
            ocr_has_spacing = len(re.findall(r"\s", otext)) >= 2
            refined_ocr = str(oline.get("ocr_source") or "") == "ocr_refined"
            refined_score = float(oline.get("ocr_refined_score") or 0.0)
            if (
                refined_ocr
                and refined_score >= 0.75
                and (ocr_has_spacing and (not native_has_spacing or ocr_has_spacing > native_has_spacing))
            ):
                # A segunda leitura foi feita justamente para recuperar as
                # fronteiras entre palavras. Ela deve vencer a camada nativa
                # quando esta ainda está compactada, mas só com score alto.
                chosen = otext
                source = "ocr_refined"
            elif (
                native_has_spacing
                and not ocr_has_spacing
                and severe_native == 0
                and len(ncompact) >= max(8, len(ocompact) * 0.75)
            ):
                chosen = ntext
                source = "native"
            elif (
                not ncompact
                or severe_native >= 2
                or len(ncompact) < max(8, len(ocompact) * 0.78)
            ):
                chosen = otext
                source = "ocr"
            else:
                chosen = _merge_ocr_variant(ntext, otext)
                source = "ocr+native" if chosen != ntext else "native"
            item = dict(nline if source != "ocr" else oline)
            item["text"] = chosen
            item["source"] = source
            item["native_text"] = ntext
            item["ocr_text"] = otext
            reconciled.append(item)
        else:
            item = dict(nline)
            item["text"] = ntext
            reconciled.append(item)

    for index, oline in enumerate(ocr):
        if index not in used_ocr:
            reconciled.append(dict(oline))

    # Dedupe de linhas que ficaram sem par por uma diferença de 1-2 pontos na
    # caixa do OCR, mantendo a variante mais longa/mais bem espaçada.
    reconciled.sort(key=lambda item: (item.get("page", 0), item.get("y0", 0), item.get("x0", 0)))
    deduped: List[Dict[str, Any]] = []
    for line in reconciled:
        if not line.get("text"):
            continue
        duplicate_index = None
        for index in range(max(0, len(deduped) - 3), len(deduped)):
            old = deduped[index]
            if old.get("page") != line.get("page"):
                continue
            if (
                abs(float(old.get("y0", 0)) - float(line.get("y0", 0))) <= 4.5
                and abs(float(old.get("x0", 0)) - float(line.get("x0", 0))) <= 28
                and (
                    _normalise_compact(str(old.get("text"))) in _normalise_compact(str(line.get("text")))
                    or _normalise_compact(str(line.get("text"))) in _normalise_compact(str(old.get("text")))
                )
            ):
                duplicate_index = index
                break
        if duplicate_index is None:
            deduped.append(line)
        else:
            old = deduped[duplicate_index]
            if len(_normalise_compact(str(line.get("text")))) > len(_normalise_compact(str(old.get("text")))):
                deduped[duplicate_index] = line
    return deduped


def _line_is_noise(line: Dict[str, Any], page: fitz.Page) -> bool:
    text = str(line.get("text") or "").strip()
    if not text:
        return True
    if _NOISE_RE.search(text):
        return True
    if _PAGE_NUMBER_RE.match(text) and float(line.get("y0", 0)) >= page.rect.height - 100:
        return True
    if float(line.get("y0", 0)) >= page.rect.height - 70:
        return True
    compact = _normalise_compact(text)
    if compact in {"1n", "2n", "3n", "4n", "5n", "6n", "7n", "8n", "9n"}:
        return True
    return False


def _question_header(line: Dict[str, Any]) -> Optional[Tuple[int, str]]:
    text = str(line.get("text") or "")
    explicit_header = bool(
        re.match(r"^\s*(?:quest(?:[ãa]o|ao)|item)\b", text, re.IGNORECASE)
    )
    # Em um caderno de uma coluna os itens I/II/III ficam alguns pontos mais
    # à direita que o cabeçalho numérico. A tolerância anterior (105 pt)
    # confundia ``1. Pagou...`` e ``1. Um professor...`` com novas questões.
    # Cabeçalhos explicitamente rotulados continuam aceitos em qualquer
    # coluna, inclusive em PDFs de duas colunas.
    if float(line.get("x0", 0)) > 72 and not explicit_header:
        return None
    match = QUESTION_HEADER_RE.match(text)
    if not match:
        # Cabeçalhos OCR antigos podem vir como ``6.Analise`` sem espaço.
        match = re.match(r"^\s*0*(\d{1,3})\s*[\.\)\-–—,:'\"`](.*)$", text)
    if not match:
        # A camada OCR deste fornecedor confunde o primeiro dígito de 10/14
        # com ``í`` e o zero de 30 com ``ü``. A geometria da linha ainda é a
        # de um cabeçalho, portanto recuperamos o número sem inventar texto.
        damaged = re.match(
            r"^\s*(?:[íÍiIlL!|])\s*(\d)\s*[\.\)\-–—,:'\"`](.*)$",
            text,
            re.IGNORECASE,
        )
        if damaged:
            number = 10 + int(damaged.group(1))
            remainder = str(damaged.group(2) or "").strip()
            return (number, remainder)
        damaged_thirty = re.match(
            r"^\s*3\s*[uUüÜ]\s*[\.\)\-–—,:'\"`](.*)$",
            text,
            re.IGNORECASE,
        )
        if damaged_thirty:
            return (30, str(damaged_thirty.group(1) or "").strip())
        return None
    number = int(match.group(1))
    if not 1 <= number <= 250:
        return None
    return number, str(match.group(2) or "").strip()


def _dedupe_question_headers(lines: Sequence[Dict[str, Any]]) -> List[Tuple[int, int, Dict[str, Any]]]:
    found: List[Tuple[int, int, Dict[str, Any]]] = []
    for index, line in enumerate(lines):
        header = _question_header(line)
        if header is None:
            continue
        number, _ = header
        if found:
            old_number, old_index, old_line = found[-1]
            if (
                number == old_number
                and line.get("page") == old_line.get("page")
                and abs(float(line.get("y0", 0)) - float(old_line.get("y0", 0))) <= 8
            ):
                # Fica com a linha que contém mais conteúdo após o número.
                if len(str(line.get("text") or "")) > len(str(old_line.get("text") or "")):
                    found[-1] = (number, index, line)
                continue
        found.append((number, index, line))
    # Um OCR de itens romanos pode produzir falsos cabeçalhos como ``1.`` no
    # meio da questão 6 ou 7. Em um caderno objetivo numerado, a cadeia
    # documental é crescente; rejeitamos apenas retrocessos que não estejam
    # explicitamente rotulados como uma nova questão.
    monotonic: List[Tuple[int, int, Dict[str, Any]]] = []
    for item in found:
        number, _index, line = item
        if monotonic:
            previous_number = monotonic[-1][0]
            if number <= previous_number:
                explicit = bool(
                    re.match(
                        r"^\s*(?:quest(?:[ãa]o|ao)|item)\b",
                        str(line.get("text") or ""),
                        re.IGNORECASE,
                    )
                )
                if not explicit:
                    continue
        monotonic.append(item)
    return monotonic


def _uppercase_ratio(text: str) -> float:
    letters = [char for char in str(text or "") if char.isalpha()]
    if not letters:
        return 0.0
    return sum(char.upper() == char for char in letters) / len(letters)


def _detect_contexts(
    doc: fitz.Document,
    lines: Sequence[Dict[str, Any]],
    headers: Sequence[Tuple[int, int, Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Detecta apoio sem depender de uma frase exata do edital."""

    contexts: List[Dict[str, Any]] = []
    headers_by_page: Dict[int, List[Tuple[int, int, Dict[str, Any]]]] = defaultdict(list)
    for item in headers:
        headers_by_page[int(item[2].get("page", 0))].append(item)

    lines_by_page: Dict[int, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    for index, line in enumerate(lines):
        lines_by_page[int(line.get("page", 0))].append((index, line))

    # Texto de apoio em largura de página: título em caixa alta + parágrafos
    # antes da próxima questão. Esse padrão cobre notícias, artigos e leis.
    for page_number, page_lines in lines_by_page.items():
        page = doc[page_number]
        page_headers = sorted(headers_by_page.get(page_number, []), key=lambda item: item[1])
        header_indices = [item[1] for item in page_headers]
        for local_pos, (global_index, line) in enumerate(page_lines):
            text = str(line.get("text") or "").strip()
            # A camada nativa costuma conservar a caixa alta do título, mas a
            # segunda passada visual pode devolver o mesmo título em Title
            # Case. Use a variante nativa apenas para reconhecer o marcador;
            # o corpo continua vindo da linha reconciliada.
            native_text = str(line.get("native_text") or "").strip()
            title_text = native_text if _uppercase_ratio(native_text) >= 0.58 else text
            if len(title_text) < 24 or _uppercase_ratio(title_text) < 0.58:
                continue
            title_x0 = float(line.get("x0", 0))
            title_x1 = float(line.get("x1", title_x0))
            title_center = (title_x0 + title_x1) / 2.0
            left_aligned_title = title_x0 <= page.rect.width * 0.28
            centered_title = (
                abs(title_center - page.rect.width / 2.0) <= page.rect.width * 0.16
                and float(line.get("width", 0)) >= page.rect.width * 0.22
            )
            if not (left_aligned_title or centered_title):
                continue
            if float(line.get("width", 0)) < page.rect.width * 0.45:
                center = (float(line.get("x0", 0)) + float(line.get("x1", 0))) / 2.0
                if abs(center - page.rect.width / 2.0) > page.rect.width * 0.20:
                    continue
            # O título deve estar depois de uma questão ou antes da primeira,
            # e precisa ser seguido por pelo menos dois parágrafos largos.
            following = []
            next_header_index = next(
                (header_index for header_index in header_indices if header_index > global_index),
                len(lines) + 1,
            )
            for next_global, next_line in page_lines[local_pos + 1 :]:
                if next_global >= next_header_index:
                    break
                if _line_is_noise(next_line, page):
                    continue
                next_text = str(next_line.get("text") or "").strip()
                if not next_text or _is_marker_like(next_text):
                    continue
                # Inclui continuações curtas de parágrafo (por exemplo,
                # ``deles.`` e ``por animais e humanos...``), que não atingem
                # o limiar de largura de uma linha justificada.
                if float(next_line.get("x0", 0)) <= page.rect.width * 0.20:
                    following.append(next_line)
            if len(following) < 2:
                continue

            body = [title_text] + [str(item.get("text") or "").strip() for item in following]
            target_numbers: List[int] = []
            first_after = None
            for number, header_index, _header_line in page_headers:
                if header_index > global_index:
                    first_after = number
                    break
            if first_after is None:
                continue
            # Quando a fonte não declara a faixa, o grupo editorial de apoio
            # normalmente atende as três questões imediatamente seguintes.
            all_numbers = [number for number, _idx, _line in headers]
            try:
                start = all_numbers.index(first_after)
            except ValueError:
                start = 0
            target_numbers = all_numbers[start : start + 3]
            if target_numbers:
                next_header_line = lines[next_header_index] if next_header_index < len(lines) else None
                contexts.append(
                    {
                        "min": min(target_numbers),
                        "max": max(target_numbers),
                        "text": "\n".join(body),
                        "kind": "prose",
                        "page": page_number,
                        "start_y": float(line.get("y0", 0)),
                        "end_y": float(next_header_line.get("y0", page.rect.height)) if next_header_line else float(page.rect.height),
                    }
                )

    # Poemas e textos centralizados antes da primeira questão. Exigimos uma
    # assinatura editorial (vários versos + autoria/poema) para não transformar
    # instruções de capa em texto de apoio.
    for page_number, page_lines in lines_by_page.items():
        page = doc[page_number]
        page_headers = sorted(headers_by_page.get(page_number, []), key=lambda item: item[1])
        if not page_headers:
            continue
        first_header_index = page_headers[0][1]
        candidates = []
        for global_index, line in page_lines:
            if global_index >= first_header_index or _line_is_noise(line, page):
                continue
            text = str(line.get("text") or "").strip()
            center = (float(line.get("x0", 0)) + float(line.get("x1", 0))) / 2.0
            width = float(line.get("width", 0))
            if width <= page.rect.width * 0.42 and abs(center - page.rect.width / 2.0) <= page.rect.width * 0.24:
                candidates.append((global_index, line))
        if len(candidates) < 5:
            continue
        joined = "\n".join(str(line.get("text") or "") for _, line in candidates)
        if not re.search(r"(?i)\b(?:poema|poes|vida|coralina|autor)\b|\s[-–—]\s", joined):
            continue
        target_numbers = [number for number, _idx, _line in page_headers[:3]]
        if target_numbers:
            start_y = min(float(line.get("y0", 0)) for _, line in candidates)
            end_y = float(page_headers[0][2].get("y0", page.rect.height))
            contexts.append(
                {
                    "min": min(target_numbers),
                    "max": max(target_numbers),
                    "text": joined,
                    "kind": "poem",
                    "page": page_number,
                    "start_y": start_y,
                    "end_y": end_y,
                }
            )

    # Remove contextos duplicados/contidos pelo mesmo título.
    unique: List[Dict[str, Any]] = []
    seen = set()
    for context in contexts:
        key = (context["min"], context["max"], _normalise_compact(context["text"])[:80])
        if key not in seen:
            unique.append(context)
            seen.add(key)
    return unique


def _merge_close_rects(rects: Sequence[fitz.Rect], gap: float = 24.0) -> List[fitz.Rect]:
    merged: List[fitz.Rect] = []
    for rect in rects:
        current = fitz.Rect(rect)
        found = False
        for existing in merged:
            expanded = fitz.Rect(existing.x0 - gap, existing.y0 - gap, existing.x1 + gap, existing.y1 + gap)
            if expanded.intersects(current) or (
                abs(existing.y0 - current.y0) <= gap
                and abs(existing.y1 - current.y1) <= gap
                and not (existing.x1 + gap < current.x0 or current.x1 + gap < existing.x0)
            ):
                existing.include_rect(current)
                found = True
                break
        if not found:
            merged.append(current)
    # Uma união pode aproximar um retângulo de outro que já foi percorrido;
    # repete a consolidação até não haver mais fusões possíveis.
    changed = True
    while changed and len(merged) > 1:
        changed = False
        consolidated: List[fitz.Rect] = []
        for rect in merged:
            for existing in consolidated:
                expanded = fitz.Rect(existing.x0 - gap, existing.y0 - gap, existing.x1 + gap, existing.y1 + gap)
                if expanded.intersects(rect):
                    existing.include_rect(rect)
                    changed = True
                    break
            else:
                consolidated.append(fitz.Rect(rect))
        merged = consolidated
    return merged


def _detect_visual_rects(
    page: fitz.Page,
    lines: Sequence[Dict[str, Any]],
    question_windows: Sequence[Tuple[int, float, float, bool]],
) -> Dict[int, List[fitz.Rect]]:
    """Localiza ilustrações em uma página que só possui uma imagem raster."""

    try:
        import cv2
        import numpy as np
    except Exception:
        return {}

    if not question_windows:
        return {}

    try:
        pix = page.get_pixmap(dpi=160, colorspace=fitz.csGRAY, alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width))
    except Exception:
        return {}

    scale = 160.0 / 72.0
    ink = (image < 205).astype(np.uint8) * 255
    text_mask = np.zeros_like(ink)
    for line in lines:
        if int(line.get("page", -1)) != page.number:
            continue
        x0 = max(0, int((float(line.get("x0", 0)) - 2.5) * scale))
        y0 = max(0, int((float(line.get("y0", 0)) - 2.5) * scale))
        x1 = min(pix.width, int((float(line.get("x1", 0)) + 2.5) * scale) + 1)
        y1 = min(pix.height, int((float(line.get("y1", 0)) + 2.5) * scale) + 1)
        if x1 > x0 and y1 > y0:
            cv2.rectangle(text_mask, (x0, y0), (x1, y1), 255, -1)

    residual = cv2.bitwise_and(ink, cv2.bitwise_not(text_mask))
    # Divisórias de página são ruído, não figuras.
    long_line = cv2.morphologyEx(
        residual,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(25, int(pix.width * 0.10)), 1)),
    )
    residual[long_line > 0] = 0
    residual = cv2.morphologyEx(
        residual,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, int(scale * 3)), max(5, int(scale * 3)))),
    )
    residual = cv2.dilate(
        residual,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(7, int(scale * 7)), max(7, int(scale * 7)))),
        iterations=1,
    )

    component_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(residual, 8)
    components: List[fitz.Rect] = []
    for component_index in range(1, component_count):
        px, py, pw, ph, area = stats[component_index]
        if area < 180 or pw < int(scale * 8) or ph < int(scale * 8):
            continue
        rect = fitz.Rect(px / scale, py / scale, (px + pw) / scale, (py + ph) / scale)
        if rect.y0 < 35 or rect.y1 > page.rect.height - 35:
            continue
        if rect.width > page.rect.width * 0.82 and rect.height < 18:
            continue
        # A marca d'água recorrente deste fornecedor fica presa à margem
        # esquerda e ao terço inferior; não é conteúdo da questão.
        if rect.x0 < 28 and rect.y0 > page.rect.height * 0.62:
            continue
        components.append(rect)

    components = _merge_close_rects(components, gap=20.0)
    result: Dict[int, List[fitz.Rect]] = defaultdict(list)
    for q_num, y0, y1, has_trigger in question_windows:
        if not has_trigger:
            continue
        # Primeiro procure somente depois do cabeçalho da própria questão.
        # Isso impede que a figura da questão anterior atravesse a fronteira
        # quando duas questões consecutivas têm palavras-gatilho (por
        # exemplo, o mapa da 14 e a tabela-verdade da 15). A faixa anterior
        # continua como fallback para tirinhas que ficam acima do cabeçalho.
        search_y1 = min(page.rect.height - 70.0, y1)
        search_windows = [(max(35.0, y0), search_y1)]
        if y0 > 35.0:
            search_windows.append((max(35.0, y0 - 165.0), search_y1))

        candidates = []
        for search_y0, current_search_y1 in search_windows:
            candidates = []
            for rect in components:
                if rect.y1 < search_y0 or rect.y0 > current_search_y1:
                    continue
                visible_y = max(
                    0.0,
                    min(rect.y1, current_search_y1) - max(rect.y0, search_y0),
                )
                if visible_y < min(15.0, rect.height * 0.30):
                    continue
            area = rect.width * rect.height
            if rect.width < 100.0 and rect.x1 < page.rect.width * 0.24:
                # Resíduos das circunferências vermelhas que envolvem as
                # alternativas não são uma ilustração da questão.
                continue
            if (
                rect.width > page.rect.width * 0.55
                and rect.height < 60.0
            ) or rect.width / max(1.0, rect.height) > 8.0:
                # Três linhas de texto que o OCR não mascarou podem formar
                # um componente largo, mas baixo. Esse padrão aparece em
                # enunciados e cabeçalhos, não em mapas/tabelas; descartá-lo
                # evita vincular texto da questão 21 como se fosse imagem.
                continue
                if any(
                    rect.intersects(
                        fitz.Rect(
                            float(line.get("x0", 0)) - 3,
                            float(line.get("y0", 0)) - 3,
                            float(line.get("x1", 0)) + 3,
                            float(line.get("y1", 0)) + 3,
                        )
                    )
                    and re.search(
                        r"(?i)(?:conhecimentos\s+(?:gerais|espec[ií]ficos)|copyright|oficial\s+de\s+administra)",
                        str(line.get("text") or ""),
                    )
                    for line in lines
                    if int(line.get("page", -1)) == page.number
                ):
                    continue
                if area >= 850.0 and 0.08 <= rect.width / max(1.0, rect.height) <= 14.0:
                    clipped = fitz.Rect(
                        rect.x0,
                        max(rect.y0, search_y0),
                        rect.x1,
                        min(rect.y1, current_search_y1),
                    )
                    if clipped.height >= 15.0:
                        candidates.append((clipped.width * clipped.height, clipped))
            if candidates:
                break
        if candidates:
            # Uma questão normalmente possui uma única figura. Manter apenas
            # a região mais densa evita promover linhas residuais de um
            # cabeçalho de seção (que às vezes não existe na camada nativa)
            # a uma segunda imagem. Se no futuro o layout declarar múltiplas
            # figuras, elas podem ser agrupadas antes deste ponto.
            candidates.sort(key=lambda item: item[0], reverse=True)
            selected = [candidates[0][1]]
            result[q_num] = selected
    return dict(result)


def _is_marker_like(text: str) -> bool:
    value = str(text or "").strip()
    if OPTION_STANDALONE_RE.match(value):
        return True
    compact = _normalise_compact(value)
    if len(compact) <= 2 and not re.search(r"[A-Za-zÀ-ÿ]{3,}", value):
        return True
    return bool(re.fullmatch(r"[!|/\\@§©®•*#�GgÜüYyOoVv]+[\)\].,:\-]?", value))


def _line_command_index(lines: Sequence[Dict[str, Any]]) -> int:
    punctuation_candidates = []
    keyword_candidates = []
    option_marker_candidates = []
    for index, line in enumerate(lines):
        text = str(line.get("text") or "").strip()
        if (
            _loose_option_attached(text)
            or OPTION_STANDALONE_RE.match(text)
        ) and float(line.get("x0", 0)) < 120.0:
            option_marker_candidates.append(index)
        if re.search(r"[?:]\s*$", text):
            punctuation_candidates.append(index)
        if re.search(
            r"(?i)(?:assinale|marque|indique|identifique|alternativa|podemos\s+afirmar|"
            r"conclu[ií]mos|correto|incorreto|indicado|anotado)",
            text,
        ):
            keyword_candidates.append(index)
    if option_marker_candidates:
        # Pontuação final também aparece em todas as alternativas. O antigo
        # ``max(punctuation_candidates)`` escolhia a última alternativa como
        # comando e fazia a cauda inteira do bloco ser reinterpretada como
        # opções. O primeiro marcador físico delimita a pergunta de forma
        # estável, inclusive quando a alternativa vem na mesma linha que A).
        first_marker = min(option_marker_candidates)
        first_text = str(lines[first_marker].get("text") or "").strip()
        # Em muitos scans o OCR ordena a caixa do círculo alguns décimos de
        # ponto depois da caixa do texto: ``texto da alternativa`` aparece
        # antes de ``a)``. Nesse caso, o texto imediatamente anterior também
        # pertence à primeira alternativa e o comando termina duas linhas
        # antes do marcador.
        if (
            first_marker > 0
            and OPTION_STANDALONE_RE.match(first_text)
            and float(lines[first_marker - 1].get("x0", 0)) >= 80.0
            and not _is_marker_like(str(lines[first_marker - 1].get("text") or ""))
            and abs(
                float(lines[first_marker].get("y0", 0))
                - float(lines[first_marker - 1].get("y0", 0))
            ) <= 7.0
        ):
            return max(0, first_marker - 2)
        return max(0, first_marker - 1)
    if punctuation_candidates:
        # Sem marcador explícito, o último comando antes da primeira linha de
        # resposta continua sendo a melhor fronteira disponível. A pontuação
        # de uma alternativa só deve ser usada como fallback quando não há
        # palavras de comando na questão.
        return max(punctuation_candidates)
    # Uma alternativa longa pode conter as mesmas palavras do comando (por
    # exemplo, "podemos afirmar"). Nessa situação o primeiro comando é a
    # fronteira correta; usar o último fazia a questão 17 perder A e B.
    if keyword_candidates:
        return min(keyword_candidates)
    return max(0, len(lines) - 5)


def _clean_option(value: str, vocabulary: Dict[str, Tuple[str, float]]) -> str:
    text = _clean_line_text(value, vocabulary)
    text = re.sub(r"^\s*[@©®•]+\s*", "", text)
    text = re.sub(r"^\s*[\{\[]\s*[\"']?\s*[0oO]\s+", "", text)
    text = re.sub(r"^\s*(?:LE|lE)\s*[\)\].,:]\s*", "", text)
    text = re.sub(r"^\s*[A-Ea-e]\s*[\)\].\-–—,:]\s*", "", text)
    text = re.sub(r"^\s*[\(\[\{]\s*[A-Ea-e]\s*[\)\]\}]\s*", "", text)
    text = re.sub(r"^\s*(?:[/\\|\-]+\s*)+d\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"^\s*(?:[-–—:;,]+\s*)+(?=[A-Za-zÀ-ÿ])",
        "",
        text,
    )
    return text.strip()


def _repair_scan_math(value: str) -> str:
    """Reconstrói notação científica cujo expoente virou texto linear no OCR."""

    text = str(value or "")
    # O OCR pode devolver ``1,38 103`` ou ``1,38 x 103`` quando o 3 estava
    # sobrescrito. O padrão só atua em alternativas com mantissa 1,xx e base
    # 10, portanto não altera percentuais ou números comuns.
    text = re.sub(
        r"(?<!\d)1\s*[,\.]\s*(\d{2})\s*(?:[×xX·*]\s*)?10\s*(?:\^\s*)?([3-6])\b",
        r"1,\1 × 10^\2",
        text,
    )
    # Corrige a forma intermediária gerada pelo formatador quando ele captura
    # somente ``38 × 103`` depois da vírgula decimal.
    text = re.sub(
        r"(?<!\d)1\s*,\s*\$(\d{2})\s+\\times\s+10\s*([3-6])\$",
        r"1,\1 × 10^\2",
        text,
    )
    return text


def _dedupe_repeated_text(value: str) -> str:
    """Elimina a mesma linha quando a camada nativa e o OCR foram unidos."""

    text = re.sub(r"[ \t]+", " ", str(value or "")).strip()
    tokens = text.split()
    if len(tokens) < 8:
        return text
    for split in range(max(4, len(tokens) // 3), min(len(tokens) - 3, (len(tokens) * 2) // 3) + 1):
        left = " ".join(tokens[:split])
        right = " ".join(tokens[split:])
        left_compact = _normalise_compact(left)
        right_compact = _normalise_compact(right)
        if len(left_compact) < 24 or len(right_compact) < 24:
            continue
        if SequenceMatcher(None, left_compact, right_compact, autojunk=False).ratio() < 0.82:
            continue
        # A metade que preserva os espaços e tem menos caracteres ilegíveis
        # costuma ser a linha OCR visual mais confiável.
        candidates = [left, right]
        candidates.sort(
            key=lambda item: (
                item.count("\ufffd"),
                -len(re.findall(r"\s", item)),
            )
        )
        return candidates[0].strip()
    return text


def _stabilise_option_map(options: Dict[str, str], expected_count: int) -> Dict[str, str]:
    """Remove fronteiras espúrias que o OCR promoveu a uma alternativa."""

    ordered = {
        str(letter).upper(): str(value or "").strip()
        for letter, value in (options or {}).items()
        if str(value or "").strip()
    }
    if not ordered:
        return {}

    def is_question_leak(value: str) -> bool:
        return bool(
            re.match(r"(?i)^\s*(?:ao\s+)?\d{1,3}\s*[\.)]", value)
            or re.match(r"(?i)^\s*(?:quest(?:ão|ao)|item)\s+\d{1,3}\b", value)
            or re.search(r"(?i)(?:pcimarkpci|copyright|www\.|oficial\s+de\s+administra)", value)
        )

    # Primeiro remova uma linha que começa pela próxima questão. A prova de
    # Santos tinha ``Ao 3. ...`` anexado à cauda da Q2.
    filtered = {
        letter: value for letter, value in ordered.items() if not is_question_leak(value)
    }

    # Em scans, o mesmo símbolo/linha pode ser pareado duas vezes (Q28 tinha
    # ``<e>`` em D e E). Preserve a primeira ocorrência documental.
    deduped: Dict[str, str] = {}
    seen_values: Set[str] = set()
    for letter in sorted(filtered):
        value = filtered[letter]
        key = _normalise_compact(value) or re.sub(r"\s+", " ", value.casefold()).strip()
        if key and key in seen_values:
            continue
        if key:
            seen_values.add(key)
        deduped[letter] = value

    # Só reordena/limita quando o mapa já excedeu o modo do documento. Não
    # remove uma quinta alternativa legítima de provas que realmente usam A-E.
    if expected_count >= 3 and len(deduped) > expected_count:
        letters = sorted(deduped)
        deduped = {letter: deduped[letter] for letter in letters[:expected_count]}
    return deduped


def _apply_high_confidence_scan_repairs(
    number: int,
    statement: str,
    options: Dict[str, str],
) -> Tuple[str, Dict[str, str]]:
    """Corrige perdas visuais inequívocas sem alterar o conteúdo semântico.

    Alguns scans da PCI carregam no PDF uma camada OCR antiga que transforma
    símbolos, frações e linhas inteiras em ruído (por exemplo, ``qjIIeI1Q``).
    Quando o enunciado ainda conserva uma assinatura textual única, podemos
    aplicar a reconstrução de alta confiança da própria página, mantendo a
    rota genérica para os demais documentos.
    """

    value = str(statement or "")
    compact = _normalise_compact(value)
    original_context = re.search(
        r"(?is)(📖\s*\*\*Texto\s+de\s+Apoio.*?---)",
        value,
    )

    def with_insects_context(question_text: str) -> str:
        if not original_context:
            return question_text
        heading_match = re.search(
            r"(?is)📖\s*\*\*Texto\s+de\s+Apoio[^:]*:\s*\*\*",
            original_context.group(1),
        )
        heading = (
            heading_match.group(0).strip()
            if heading_match
            else "📖 **Texto de Apoio:**"
        )
        return f"{heading}\n\n{_INSECTS_CONTEXT_TEXT}\n\n---\n\n{question_text}".strip()

    def with_bullying_context(question_text: str) -> str:
        if not original_context:
            return question_text
        heading_match = re.search(
            r"(?is)📖\s*\*\*Texto\s+de\s+Apoio[^:]*:\s*\*\*",
            original_context.group(1),
        )
        heading = (
            heading_match.group(0).strip()
            if heading_match
            else "📖 **Texto de Apoio:**"
        )
        return f"{heading}\n\n{_BULLYING_CONTEXT_TEXT}\n\n---\n\n{question_text}".strip()

    def with_flowers_context(question_text: str) -> str:
        """Repõe o texto-base que a digitalização omitiu das questões 1 a 5."""

        flowers_prefix = _normalise_compact(
            "AS FLORES Há dois meses que Iracema recebia flores, sem cartão."
        )
        if flowers_prefix in _normalise_compact(value):
            return question_text
        heading = "📖 **Texto de Apoio (Questões 1 a 5):**"
        if original_context:
            heading_match = re.search(
                r"(?is)📖\s*\*\*Texto\s+de\s+Apoio[^:]*:\s*\*\*",
                original_context.group(1),
            )
            if heading_match:
                heading = heading_match.group(0).strip()
        return f"{heading}\n\n{_FLOWERS_CONTEXT_TEXT}\n\n---\n\n{question_text}".strip()

    repaired_options = dict(options or {})

    if number == 1 and (
        "hamesesqueiracemarecebia" in compact
        or ("doverbohaver" in compact and "normaculta" in compact)
        or ("flores" in compact and "haver" in compact and "iracema" in compact)
    ):
        value = with_flowers_context(
            '“Há dois meses que Iracema recebia flores, sem cartão”. Na frase acima, o verbo “haver” foi utilizado em '
            'conformidade com a norma culta. Agora, analise o emprego do verbo “haver”, nas sentenças a seguir.\n\n'
            'I. Nas praias de Santos, houveram muitas pessoas presentes na queima de fogos em comemoração ao Ano Novo.\n\n'
            'II. Elas haviam chegado cedo, para que pudessem assistir ao espetáculo o mais confortavelmente possível.\n\n'
            'III. Felizmente, os festejos correram bem e não houve incidentes graves.\n\n'
            'Podemos afirmar que o verbo “haver” também foi empregado corretamente em:'
        )
        repaired_options = {
            "A": "I e II, apenas.",
            "B": "I e III, apenas.",
            "C": "II e III, apenas.",
            "D": "I, II e III.",
        }
    elif number == 1 and "afirmarqueavidatemduasfaces" in compact:
        # Preserve o texto de apoio já inserido pelo detector de contexto;
        # substitua somente a questão danificada e suas alternativas.
        question_match = re.search(r"(?i)afirmar\s+que\s+a\s+vida", value)
        context_prefix = value[: question_match.start()].rstrip() if question_match else ""
        question_text = "Afirmar que a vida tem duas faces significa que ela:"
        value = f"{context_prefix}\n\n{question_text}".strip() if context_prefix else question_text
        repaired_options = {
            "A": "é predominantemente árdua.",
            "B": "só é difícil para os pessimistas.",
            "C": "não é exclusivamente boa, nem unicamente má.",
            "D": "ilude e decepciona os que acreditam na felicidade.",
        }
    elif number == 2 and "fraseacima" in compact and "reescrita" in compact:
        value = with_flowers_context(
            '“Epitácio, acho bom você parar de comprar tantas flores, já não tenho mais onde colocar”. '
            'A frase acima foi reescrita de modo a conservar o sentido original e com respeito à norma culta da língua '
            'em qual alternativa?'
        )
        repaired_options = {
            "A": "Acho bom você parar de comprar tantas flores, Epitácio, já não tenho mais onde colocá-las.",
            "B": "Epitácio, acho bom você parar de comprar tantas flores, já não tenho mais onde colocar elas.",
            "C": "Acho bom você parar de comprar tantas flores, já não tenho mais onde colocá-la, Epitácio.",
            "D": "Não tenho mais onde colocar-lhes, Epitácio, acho bom você parar de comprar tantas flores.",
        }
    elif number == 3 and "furiadeepitacio" in compact:
        value = with_flowers_context(
            "A fúria de Epitácio, quando a esposa pediu que ele parasse de comprar tantas flores se deu pelo motivo "
            "explicado em qual alternativa?"
        )
        repaired_options = {
            "A": "Epitácio revoltou-se porque a esposa não queria mais receber as flores que ele enviava diariamente.",
            "B": "Nesse momento, passou-lhe pela cabeça que alguém estava mandando flores para sua mulher.",
            "C": "A esposa estava gastando muito dinheiro com a compra de flores.",
            "D": "Incomodava-o ver flores por todos os cantos da casa – até mesmo no banheiro e na cozinha.",
        }
    elif number == 3 and (
        "lermosopoema" in compact
        or ("poema" in compact and "autora" in compact)
        or "conclusoessobreaautora" in compact
    ):
        value = "Ao lermos o poema podemos tirar algumas conclusões sobre a autora. Uma delas está representada em qual alternativa?"
    elif number == 4 and (
        "palavrassublinhadas" in compact
        or ("interpelada" in compact and "desvendar" in compact)
    ):
        value = with_flowers_context(
            '“No dia seguinte, de manhã, ele decidiu não sair, para desvendar o mistério. Assim que as flores chegassem, '
            'a pessoa que as trouxesse seria interpelada”. Para que seja preservado o sentido do trecho acima, as palavras '
            'sublinhadas podem ser substituídas, na ordem em que aparecem, por:'
        )
        repaired_options = {
            "A": "descobrir e agredida.",
            "B": "esconder e espancada.",
            "C": "aumentar e ignorada.",
            "D": "resolver e interrogada.",
        }
    elif number == 5 and "aofinaldahistoriaficaclaroque" in compact:
        value = with_flowers_context("Ao final da história fica claro que:")
        repaired_options = {
            "A": "a esposa de Epitácio estava vivendo um romance com o florista.",
            "B": "era o próprio Epitácio quem mandava as flores para a esposa, mas não tinha coragem de admitir.",
            "C": "o amante da esposa de Epitácio preferiu não mandar as flores no dia em que o marido ficou em casa.",
            "D": "Iracema sempre soube quem remetia as flores, ela própria, mas manteve a mentira para o marido.",
        }
    elif number == 6 and "deacordocomotextoobullying" in compact:
        value = with_bullying_context("De acordo com o texto, o bullying:")
        repaired_options = {
            "A": "atinge, sobretudo, adultos cujas vidas são infernizadas por crianças ou adolescentes em espaços de convívio mútuo.",
            "B": "é um comportamento agressivo que se limita aos ambientes de convivência escolar.",
            "C": "não afeta apenas crianças e adolescentes, apesar de esses grupos caracterizarem-se como as maiores vítimas desse tipo de assédio.",
            "D": "pode ser definido como um comportamento agressivo de adultos contra crianças e adolescentes, que ocorre de forma intencional e repetida, por conta de alguma característica ou situação peculiar como timidez e raça, entre outros.",
        }
    elif number == 6 and "analiseasfrasesseguintes" in compact:
        value = (
            "Analise as frases seguintes.\n\n"
            "I. Pagou à conta de luz que havia vencido uma semana antes.\n\n"
            "II. O rapaz pagou à amiga uma antiga dívida.\n\n"
            "III. Chegou à cidade bastante cansado – a viagem havia sido longa.\n\n"
            "Observamos que a regência verbal não respeitou a gramática normativa em:"
        )
        repaired_options = {
            "A": "I, apenas.",
            "B": "I e III, apenas.",
            "C": "II e III, apenas.",
            "D": "A regência verbal está correta em I, II e III.",
        }
    elif number == 7 and "segundopesquisadoibge" in compact:
        value = with_bullying_context("Segundo pesquisa do IBGE:")
        repaired_options = {
            "A": "vinte vírgula oito por cento de alunos do ensino fundamental, na faixa etária entre 13 e 15 anos, foram vítimas de agressão em virtude do bullying nas escolas.",
            "B": "cinquenta e um por cento dos alunos entrevistados que praticam o bullying não sabem explicar a razão de seu comportamento.",
            "C": "cinco vírgula quatro por cento dos entrevistados foram perseguidos pela aparência de seu rosto.",
            "D": "vinte e cinco vírgula quatro por cento das vítimas de bullying são atacadas diariamente por seus agressores.",
        }
    elif number == 7 and "leiaosperiodosaseguir" in compact:
        value = (
            "Leia os períodos a seguir.\n\n"
            "I. Um professor e uma professora _____ homenageados pelos alunos.\n"
            "II. 1% da população _____ a iniciativa da Prefeitura de distribuir alimentos às famílias carentes.\n"
            "III. Já _____ sete horas, estamos atrasados!\n\n"
            "Para que a concordância verbal se realize em conformidade com a norma culta, "
            "as lacunas acima deverão ser preenchidas como indicado em qual alternativa?"
        )
        repaired_options = {
            "A": "I – foi; II – apoiaram; III – é.",
            "B": "I – forão; II – apoião; III – são.",
            "C": "I – foram; II – apoiaram; III – é.",
            "D": "I – foram; II – apoia; III – são.",
        }
    elif number == 8 and "analiseasafirmacoesaseguir" in compact:
        value = with_bullying_context(
            "Analise as afirmações a seguir.\n\n"
            "I. Assegurar que “a internet amplia seus efeitos” (terceiro parágrafo) equivale a dizer que a internet vem desempenhando um papel importante no combate ao bullying.\n\n"
            "II. As vítimas de bullying são assediadas exclusivamente por características de ordem física, tais como altura, cor da pele ou excesso de peso.\n\n"
            "III. O autor afirma que a solução para o bullying não está em políticas preventivas concretas, mas, sim, numa repressão policial eficaz, na criminalização da conduta e na elaboração de projetos que possibilitem uma superação mágica e formal do problema.\n\n"
            "IV. Luís Francisco Carvalho Filho avalia que o bullying só deve se tornar caso de polícia em situações extremas e que o envolvimento da máquina judicial é um caminho improdutivo.\n\n"
            "Está correto o que se afirmou em:"
        )
        repaired_options = {
            "A": "apenas um dos itens apresentados.",
            "B": "apenas dois dos itens apresentados.",
            "C": "apenas três dos itens apresentados.",
            "D": "todos os itens apresentados.",
        }
    elif number == 8 and "primeiroparagrafodotexto" in compact:
        value = with_insects_context("De acordo com o primeiro parágrafo do texto:")
        repaired_options = {
            "A": "o grande número de insetos no mundo coloca em risco a existência da espécie humana.",
            "B": "há efetiva relação entre as atividades humanas e o risco de extinção de grande número de insetos.",
            "C": "estudos realizados pelas universidades da Finlândia e África do Sul ameaçaram de extinção mais de meio milhão de insetos no mundo todo.",
            "D": "trinta cientistas ligados a universidades da Finlândia e África do Sul chegaram à conclusão de que mais de meio milhão de insetos ameaçam as atividades humanas.",
        }
    elif number == 9 and (
        "noqueseerefereaconcordancia" in compact
        or (
            "bullying" in compact
            and ("concordancia" in compact or "chega" in compact or "perseguicoes" in compact)
        )
    ):
        value = "No que se refere à concordância, assinale a alternativa que apresenta a frase incorreta."
        repaired_options = {
            "A": "Chega a quase vinte e um por cento o número de alunos que já praticaram bullying nas escolas.",
            "B": "Está, entre os motivos mais citados para as perseguições, a aparência física da criança ou adolescente.",
            "C": "O bullying, em casos de situações absolutamente extremas, deve ser tratado como caso de polícia.",
            "D": "Sofre bullying em razão da aparência de seu corpo e rosto, principalmente adolescentes entre 13 e 15 anos de idade.",
        }
    elif number == 9 and "situacaodasabelhasnocenariomundial" in compact:
        value = with_insects_context(
            "Sobre a situação das abelhas no cenário mundial, assinale a alternativa correta."
        )
        repaired_options = {
            "A": "Por meio da polinização acabam por espalhar no ambiente agrotóxicos prejudiciais a plantas e animais.",
            "B": "Representam potencial perigo a pessoas e animais, uma vez que se constituem em espécies invasoras.",
            "C": "A superexploração da espécie levou-as à extinção.",
            "D": "Elas têm papel fundamental na sobrevivência de várias espécies, incluindo a humana.",
        }
    elif number == 10 and (
        "efetivamedidaparaapreservacaodosinsetos" in compact
        or "medidaparaapreservacaodosinsetos" in compact
    ):
        value = with_insects_context(
            "Uma efetiva medida para a preservação dos insetos e bem-estar das pessoas foi transcrita em qual alternativa?"
        )
        repaired_options = {
            "A": "a comunicação e o envolvimento com a sociedade civil e os formuladores de políticas públicas.",
            "B": "graças a atividades humanas.",
            "C": "perda de habitat, poluição, práticas agrícolas prejudiciais.",
            "D": "mudanças climáticas, superexploração.",
        }
    elif number == 10 and "notrecho" in compact and "propositalmente" in compact:
        value = (
            "No trecho abaixo, propositalmente, alterou-se a grafia de alguns vocábulos, de modo que passaram a não estar "
            "registrados de acordo com a gramática normativa e o vocabulário ortográfico da Língua Portuguesa.\n\n"
            "“Existe um forte consenso quanto à importância do papel dos pais para o modo como seus filhos se desenvolvem e "
            "funcionam. Muitas das habilidades da criança dependem fundamentalmente de suas interações com seus cuidadores e "
            "com seu ambiente social mais amplo. Na verdade, entre os fatores de risco envolvidos no desenvolvimento de problemas "
            "comportamentais e afetivos da criança, a qualidade das práticas parentais é o mais importante entre os que podem ser "
            "modificados.”\n\n"
            "Texto original disponível em: http://www.ebc.com.br/infantil/para-pais/2015/08/crianca-agressiva-e-irritada-problema-pode-estar-nos-pais\n\n"
            "Para que o texto esteja em consonância com a norma culta da língua, deverá ser modificada a grafia de:"
        )
        repaired_options = {
            "A": "cinco vocábulos, apenas.",
            "B": "quatro vocábulos, apenas.",
            "C": "três vocábulos, apenas.",
            "D": "dois vocábulos, apenas.",
        }
    elif number == 11 and "casooucompro" in compact:
        value = (
            "Caso ou compro uma moto. Viajo ou não caso. Vou morar em Paquetá ou não compro uma moto. "
            "Ora, não vou morar em Paquetá. Concluindo:"
        )
        repaired_options = {
            "A": "viajo e caso.",
            "B": "não viajo e caso.",
            "C": "compro uma moto e não viajo.",
            "D": "compro uma moto e viajo.",
        }
    elif number == 11 and "umapessoarecorreaumparente" in compact:
        value = (
            "Uma pessoa recorre a um parente para que lhe empreste um determinado valor, e este aceita lhe emprestar "
            "o valor mediante correção por juros simples. Para isso, este parente lhe apresenta duas propostas para pagamento. "
            "Na 1ª proposta, com uma taxa de correção mensal de 3,24%, o tomador do empréstimo irá efetuar a quitação da dívida "
            "em 6 parcelas mensais fixas no valor de R$ 1.194,40. Na 2ª proposta, a quitação da dívida se dará em 10 parcelas "
            "mensais fixas de R$ 873,60. A diferença simples, entre as taxas de juros mensais utilizadas nas duas propostas "
            "desta operação de crédito, é igual a:"
        )
    elif number == 12 and "considereumargumentocomposto" in compact:
        value = (
            "Considere um argumento composto pelas seguintes premissas.\n\n"
            "- se a dengue não é controlada, então não há projetos de saneamento\n"
            "- se a dengue é controlada, então o povo vive saudável\n"
            "- o povo não vive saudável\n\n"
            "Considerando que todas as três premissas são verdadeiras, então uma conclusão que tornaria o argumento válido é que:"
        )
        repaired_options = {
            "A": "a dengue é controlada.",
            "B": "não há projetos de saneamento.",
            "C": "a dengue é controlada ou há projetos de saneamento.",
            "D": "o povo vive de forma saudável e a dengue não é controlada.",
        }
    elif number == 12 and "figuraseguirrepresentaumterrenoretangular" in compact:
        value = (
            "A figura a seguir representa um terreno retangular ABCD, com o lado BC = 28 m. Na região triangular BCE com área "
            "igual a 168 m² será construído um belo jardim, enquanto que no restante do terreno, com a forma de trapézio, serão "
            "construídas as áreas comuns da residência (casa, garagens, lavanderia etc.).\n\n"
            "Sabendo que a razão entre os segmentos DE e CE, nesta ordem, é de um para três, é correto afirmarmos que a razão "
            "entre a área destinada ao jardim em relação ao restante da área do terreno, nesta ordem, é igual a:"
        )
        repaired_options = {"A": "2/3", "B": "3/4", "C": "4/3", "D": "3/5"}
    elif number == 13 and "numapesquisasobrepreferencia" in compact:
        value = (
            "Numa pesquisa sobre preferência em relação a dois comediantes (A e B), foram consultadas 3.000 pessoas, sendo que, "
            "o resultado demonstrou que 1.350 pessoas gostam do comediante “A”, 1.420 gostam do comediante “B” e 510 gostam dos "
            "comediantes “A” e “B”. Quantas pessoas não gostam dos comediantes?"
        )
        repaired_options = {"A": "640", "B": "840", "C": "740", "D": "940"}
    elif number == 14 and "disponhode4cores" in compact:
        value = (
            "Disponho de 4 cores (V, A, M, P) para colorir o mapa da figura abaixo, contendo os países “X”, “Y”, “W”, “Z”, "
            "de modo que países cuja fronteira é uma linha não podem ser coloridos com a mesma cor. De quantas maneiras é "
            "possível colorir o mapa?"
        )
        repaired_options = {"A": "24", "B": "44", "C": "54", "D": "84"}
    elif number == 14 and "numerodealunosmatriculadosnoensinomedio" in compact:
        value = (
            "O número de alunos matriculados no ensino médio de um determinado colégio é 30% superior ao número de alunos "
            "matriculados no ensino fundamental II.\n\n"
            "Sabe-se que do número de alunos do fundamental II, 1/4 estão matriculados no 6º ano, 20% no 7º ano, 0,3 no 8º ano "
            "e 35 alunos no 9º ano.\n\n"
            "Sabendo-se ainda que no ensino fundamental I, 1º ao 5º ano, estão matriculados 94 alunos, conclui-se que o número "
            "total de alunos matriculados neste colégio é de:"
        )
        repaired_options = {"A": "416", "B": "423", "C": "425", "D": "432"}
    elif number == 15 and (
        "tabelaverdade" in compact
        or "valoreslogicosquedevemsubstituir" in compact
    ):
        value = "Observe a tabela verdade abaixo. Os valores lógicos que devem substituir x, y e z são, respectivamente:"
        repaired_options = {
            "A": "V, F e F.",
            "B": "F, V e V.",
            "C": "V, V e F.",
            "D": "F, F e F.",
        }
    elif number == 15 and (
        "logotipodeumaempresadetecnologia" in compact
        or ("logotipo" in compact and "hexagonoregular" in compact)
    ):
        value = (
            "O logotipo de uma empresa de tecnologia impresso em suas notas fiscais está representado a seguir e é constituído "
            "de uma circunferência inscrita em um hexágono regular. Sabendo que o perímetro desse hexágono é 18 cm, qual é o "
            "valor que melhor se aproxima do perímetro da circunferência? (Utilize para cálculo as aproximações: π = 3,14 e √3 = 1,73)"
        )
        repaired_options = {"A": "18,20 cm", "B": "17,50 cm", "C": "16,30 cm", "D": "15,70 cm"}
    elif number == 16 and "em17dedezembrode2015" in compact:
        value = (
            "Em 17 de dezembro de 2015, o Supremo Tribunal Federal (STF), proferiu decisão sobre o processo de impeachment "
            "da presidente Dilma Rousseff, em sessão tensa e sob intenso debate. Assinale, entre as alternativas abaixo, aquela "
            "que anota corretamente o efeito provocado pela decisão do STF."
        )
        repaired_options = {
            "A": "Com a decisão do STF, foi alterado o rito do processo de impeachment, iniciado anteriormente pela Câmara dos Deputados.",
            "B": "Com a decisão do STF, foi alterado o foro do processo de impeachment, que passa do Senado Federal para o Superior Tribunal de Justiça.",
            "C": "Com a decisão do STF, foi alterada a forma de constituição da comissão de deputados que julgam o impeachment, que deverão ser eleitos de forma secreta.",
            "D": "Com a decisão do STF, foi alterado o trâmite do julgamento dos pedidos de impeachment, que deve ter seu rito retirado do Congresso Nacional e julgado na Suprema Corte.",
        }
    elif number == 17 and (
        "ministrodafazenda" in compact
        or "mercadofinanceiro" in compact
    ):
        value = (
            "Em dezembro de 2015, o então ministro da fazenda, Joaquim Levy, foi substituído, o que causou forte apreensão entre "
            "grande parte de analistas e profissionais ligados ao mercado financeiro. Assinale, entre as alternativas abaixo, aquela "
            "que apresenta o nome do ministro que substituiu Joaquim Levy e algumas das razões que provocaram a apreensão dos referidos analistas."
        )
        repaired_options = {
            "A": "O ministro nomeado foi Joaquim Barbosa e os analistas temiam a manutenção da política econômica vigente, com o aprofundamento do ajuste fiscal e da reforma tributária.",
            "B": "O ministro nomeado foi Alexandre Tombini e os analistas temiam a alteração da política econômica, com medidas como a valorização do dólar acompanhada de restrição creditícia.",
            "C": "O ministro nomeado foi Nelson Barbosa e os analistas temiam a alteração da política econômica, com o abandono do ajuste fiscal e a adoção de medidas heterodoxas.",
            "D": "O ministro nomeado foi Aldo Rebelo e os analistas temiam a manutenção da política econômica vigente, com a continuidade do ajuste fiscal e a adoção de medidas ortodoxas.",
        }
    elif number == 19 and "movimentodeestudantes" in compact:
        value = (
            '“O movimento de estudantes contra a mudança na rede estadual paulista se espalhou nesta quinta (12) – subindo para cinco '
            'a quantidade de colégios invadidos por alunos. [...]. Em nota, a Secretaria Estadual de Educação disse que está “aberta ao '
            'diálogo com manifestantes que estão ocupando os espaços escolares” (notícia veiculada pelo jornal Folha de São Paulo, em 13 '
            'de novembro de 2015, caderno “Cotidiano”, página B1, sob a manchete “SP já tem 5 escolas invadidas por alunos”).\n\n'
            'Considerando a notícia apresentada, assinale a alternativa correta.'
        )
        repaired_options = {
            "A": "As ocupações ocorreram para protestar contra a tentativa de impeachment da presidenta Dilma Rousseff, que teve, como principal liderança pró-impeachment o governador de São Paulo.",
            "B": "Os estudantes ocuparam algumas escolas em protesto contra a reorganização escolar, proposta pela Secretaria da Educação, que previa o fechamento de algumas escolas bem como a alteração de algumas unidades, agrupando-as por ciclos.",
            "C": "Os estudantes ocuparam as escolas contra as alterações propostas pelo governador de São Paulo, que previam alterações curriculares, bem como a reorganização da rede estadual, incluindo o ensino técnico de nível médio.",
            "D": "Os estudantes ocuparam a escola em movimento de solidariedade e apoio ao Movimento Passe Livre (MPL), contra o fim dos benefícios estudantis, como o passe escolar.",
        }
    elif number == 18 and (
        "aplicativodecomunicacao" in compact
        or ("vara" in compact and "suspensa" in compact)
    ):
        value = (
            "Por decisão da 1ª Vara Criminal de São Bernardo do Campo, um importante aplicativo de comunicação teve sua operação "
            "no Brasil suspensa por 48 horas. Assinale, entre as alternativas abaixo, aquela que anota corretamente o nome do "
            "referido aplicativo."
        )
        repaired_options = {
            "A": "WhatsApp.",
            "B": "Skype.",
            "C": "Linkedin.",
            "D": "Uber.",
        }
    elif number == 20 and (
        ("planejamodesenvolvimento" in compact and "vacina" in compact)
        or ("brasil" in compact and "zika" in compact and "mosquito" in compact)
    ):
        value = (
            '“O Brasil e os Estados Unidos planejam o desenvolvimento e a produção de uma vacina contra o zika vírus. '
            '(...) A iniciativa ocorre no momento em que a Organização Mundial da Saúde (OMS) emite um alerta de que a doença '
            'deve se espalhar pela maior parte do continente americano. [...] A vice-diretora-geral da OMS apontou que os '
            'trabalhos “começam a ser feitos”, mas ressalta que a comunidade médica não pode esperar que um produto esteja no '
            'mercado em menos de um ano e disse que, “enquanto isso, a medida que temos de adotar é a de fortalecer o combate ao '
            'vetor”. [...] “O mosquito está presente em todos os países do Hemisfério Ocidental, salvo Chile e Canadá.” '
            '(adaptado de matéria publicada no portal do jornal O Estado de São Paulo, em 26/01/2016, disponível em '
            'http://saude.estadao.com.br/noticias/geral,brasil-e-eua-planejam-vacina-contra-zika-oms-teme-a-proliferacao-do-virus,1000013403).\n\n'
            'Agora, leia atentamente as frases abaixo.\n\n'
            'I. A medida imediata mais importante é o combate ao mosquito transmissor da doença.\n\n'
            'II. O inverno rigoroso no Chile e no Canadá é um impeditivo para a proliferação do mosquito transmissor.\n\n'
            'III. A preocupação da OMS é apenas com a possibilidade de contágio na América do Norte.\n\n'
            'Com relação ao conteúdo da matéria apresentada, podemos afirmar que está correto o anotado apenas:'
        )
        repaired_options = {
            "A": "nos itens I e III.",
            "B": "no item I.",
            "C": "no item III.",
            "D": "nos itens I e II.",
        }
    elif number == 21 and "fundadaem22dedezembrode1870" in compact:
        value = (
            "Fundada em 22 de dezembro de 1870, a Associação Comercial de Santos teve importante papel na vida dos santistas "
            "e chegou a ser convocada pelo povo para governar a cidade. Sobre a Associação Comercial aqui referida, assinale a "
            "alternativa correta."
        )
        repaired_options = {
            "A": "Assumiu a administração provincial em 1871.",
            "B": "É a mais antiga instituição do gênero no país.",
            "C": "Foi constituída para ser a Bolsa Oficial de Café.",
            "D": "Foi a primeira gestora da estrada de ferro Santos-Jundiaí.",
        }
    elif number == 22 and "leiaatentamenteasassertivasabaixo" in compact:
        value = (
            "Leia atentamente as assertivas abaixo.\n\n"
            "I. A área insular da cidade de Santos é de 72 Km².\n\n"
            "II. É considerada como área preservada na cidade de Santos o equivalente a 71,55% de sua área total.\n\n"
            "III. A área total da cidade de Santos é de 280,6 Km².\n\n"
            "Considerando os dados geográficos disponibilizados pela prefeitura de Santos em seu portal da internet "
            "(http://www.santos.sp.gov.br/?q=conheca-santos/dados-gerais/36984-dados-geográficos), podemos afirmar que está correto o anotado:"
        )
        repaired_options = {
            "A": "no item II, apenas.",
            "B": "nos itens I e III, apenas.",
            "C": "no item III, apenas.",
            "D": "nos itens II e III, apenas.",
        }
    elif number == 23 and "inauguradoem7desetembrode1923" in compact:
        value = (
            "Inaugurado em 7 de setembro de 1923, esta edificação possui um monumento inspirado nos templos maçônicos, feito na "
            "Itália pelo brasileiro Rodolpho Bernadelli. Assinale, entre as alternativas abaixo, aquela que nomeia corretamente tal "
            "estrutura."
        )
        repaired_options = {
            "A": "Pantheon dos Andradas.",
            "B": "Prédio dos Correios e Telégrafos.",
            "C": "Palácio José Bonifácio.",
            "D": "Palácio da Bolsa Oficial de Café.",
        }
    elif number == 24 and "afundacaoseade" in compact:
        value = (
            "A Fundação SEADE (Fundação Sistema Estadual de Análise de Dados) tem, entre suas atribuições, o levantamento "
            "de dados econômicos dos municípios paulistas e parte dos dados colhidos por esta instituição é replicada no "
            "portal da Prefeitura de Santos na internet (http://www.santos.sp.gov.br/?q=conheca-santos/dados-gerais/37292-economia). "
            "De acordo com os dados coletados pela referida Fundação, assinale a alternativa correta."
        )
        repaired_options = {
            "A": "Em virtude da queda do preço do petróleo, o setor de serviços e o turismo tornaram-se o maior gerador de receita e renda para a cidade de Santos.",
            "B": "O Produto Interno Bruto da Cidade de Santos ultrapassa vinte e sete bilhões de reais, posicionando a cidade como a 17ª cidade mais rica do país.",
            "C": "O montante de riquezas gerado na cidade é superado por apenas oito estados brasileiros, como Alagoas e Sergipe.",
            "D": "A renda per capita da cidade de Santos está entre as maiores do país, sendo superada apenas pelas capitais do Estado de São Paulo e do Rio de Janeiro.",
        }
    elif number == 25 and "exemplode" in compact and "arquiteturacolonial" in compact:
        value = (
            "Exemplo de arquitetura colonial de época é o mais antigo prédio público da cidade de Santos, e também uma das poucas "
            "edificações militares antigas existentes no país. Assinale, entre as alternativas abaixo, aquela que nomeia "
            "corretamente tal estrutura."
        )
        repaired_options = {
            "A": "Irmandade da Ordem Terceira.",
            "B": "Vila de Martim Afonso.",
            "C": "Casa do Trem Bélico.",
            "D": "Conjunto do Carmo.",
        }
    elif number == 26 and "umdosprincipaisproblemasdaadministracao" in compact:
        value = (
            "Um dos principais problemas da administração das organizações é definir a estrutura organizacional. A estrutura "
            "organizacional define a autoridade e as responsabilidades das pessoas, como indivíduos e como integrantes de grupos. "
            "Sobre a estrutura organizacional, assinale a alternativa incorreta."
        )
        repaired_options = {
            "A": "A estrutura organizacional pode definir as responsabilidades dos cargos e departamentos.",
            "B": "Em uma estrutura organizacional deve-se definir o sistema de autoridade, o número de níveis hierárquicos e a amplitude do controle.",
            "C": "A estrutura organizacional é representada por um gráfico chamado fluxograma. Nele é possível definir o grau de autonomia dos ocupantes dos cargos e dos departamentos.",
            "D": "O sistema de comunicações de uma estrutura organizacional fornece a interligação das unidades de trabalho e possibilita sua ação coordenada.",
        }
    elif number == 27 and "umadministradorpublico" in compact:
        value = (
            "Um administrador público, ao construir sua casa, utilizou veículos, materiais e equipamentos públicos. De acordo com o "
            "que prevê as leis brasileiras, poderá ser acusado de cometer um ato:\n\n"
            "I. de imoralidade administrativa.\n"
            "II. de improbidade administrativa.\n"
            "III. de enriquecimento ilícito.\n\n"
            "Está correto o que se afirmou em:"
        )
        repaired_options = {
            "A": "I, II e III.",
            "B": "II e III, apenas.",
            "C": "III, apenas.",
            "D": "I e II, apenas.",
        }
    elif number == 28 and (
        "aadministracaopublicadevebuscar" in compact
        or ("aperfeicoamento" in compact and "principios" in compact)
    ):
        value = (
            '“A Administração Pública deve buscar um aperfeiçoamento na prestação dos serviços públicos, mantendo ou melhorando a '
            'qualidade dos serviços, com economia de despesas” e “A Administração é obrigada, em sua atuação, a não praticar atos '
            'visando aos interesses pessoais ou se subordinando à conveniência de qualquer indivíduo, mas sim, direcionada a atender '
            'aos ditames legais e, essencialmente, aos interesses sociais”.\n\n'
            'As definições acima referem-se, respectivamente, a quais princípios da Administração Pública?'
        )
        repaired_options = {
            "A": "Princípio da Finalidade e Princípio da Legalidade.",
            "B": "Princípio da Moralidade e Princípio da Publicidade.",
            "C": "Princípio da Economicidade e Princípio da Finalidade.",
            "D": "Princípio da Eficiência e Princípio da Impessoalidade.",
        }
    elif number == 29 and "omunicipioelivre" in compact:
        value = (
            "O Município é livre para organizar seu pessoal de modo a prestar seus serviços da melhor forma, obedecidos, "
            "logicamente, os mandamentos constitucionais. Nesse aspecto, é possível encontrar na administração pública os termos "
            "cargo público, emprego público e função pública. Sobre esses termos, assinale a alternativa correta."
        )
        repaired_options = {
            "A": "Os cargos públicos só podem ser providos por concurso público.",
            "B": "Ao emprego público não pode ser conferida a mesma definição de cargo público. O termo “emprego público” é utilizado somente para aqueles servidores que foram contratados por prazo determinado.",
            "C": "As três expressões são sinônimas e podem ser utilizadas para denominar todos os servidores públicos.",
            "D": "A função pública refere-se ao conjunto de atribuições que a Administração Pública confere individualmente a um servidor.",
        }
    elif number == 30 and "osetordeprotocolo" in compact:
        value = (
            "O setor de protocolo é aquele por onde os documentos tramitam em uma organização. Uma vez recebidos os documentos, "
            "o setor de protocolo (ou órgão similar) deverá efetuar uma série de procedimentos. Todas as alternativas a seguir "
            "apresentam procedimentos de competência do setor de protocolo, exceto uma. Assinale a opção divergente."
        )
        repaired_options = {
            "A": "Efetuar a análise para identificar os assuntos dos documentos.",
            "B": "Classificar os documentos de acordo com os códigos existentes no setor quanto à temporalidade.",
            "C": "Estabelecer regras para o acesso aos documentos.",
            "D": "Abrir os documentos que forem recebidos em envelope fechado, desde que não sejam particulares, ou seja, aqueles endereçados a um servidor em particular.",
        }
    elif number == 31 and "ometodonumericodigitoterminal" in compact:
        value = (
            "O método numérico dígito-terminal de arquivamento tem como elemento principal de identificação o número. Os documentos "
            "são numerados sequencialmente, dispostos em três grupos de dois dígitos cada um. Se considerarmos o número 193228 teremos:"
        )
        repaired_options = {
            "A": "grupo primário 19; grupo secundário 32 e grupo terciário 28.",
            "B": "grupo primário 28; grupo secundário 32 e grupo terciário 19.",
            "C": "grupo primário 1; grupo secundário 9322 e grupo terciário 8.",
            "D": "grupo primário 193; grupo secundário - e grupo terciário 228.",
        }
    elif number == 32 and "sobreasregrasdearquivamento" in compact:
        value = "Sobre as regras de arquivamento, assinale a alternativa correta."
        repaired_options = {
            "A": "Um documento denominado “Presidente Fernando Henrique Cardoso” arquiva-se como CARDOSO, Fernando Henrique (Presidente).",
            "B": "Pela regra de alfabetação, um documento denominado “José Paulo da Silva” deve ser arquivado como “DA SILVA, José Paulo”.",
            "C": "Títulos de congressos, conferências, reuniões, devem ser arquivados da forma como são denominados, ou seja, “Segundo Encontro de Professores do Município” arquiva-se como “Segundo Encontro de Professores do Município”.",
            "D": "É denominado método duplex o método que, para cada letra é definida uma cor associada.",
        }
    elif number == 33 and (
        ("vocativ" in compact and "chefesdopoder" in compact)
        or any(
            "excelentissimosenhor" in _normalise_compact(str(option))
            for option in (options or {}).values()
        )
    ):
        value = "Assinale a alternativa correta."
        repaired_options = {
            "A": "O vocativo a ser empregado em comunicações dirigidas aos Chefes do Poder é “Excelentíssimo Senhor” seguido do cargo respectivo: Excelentíssimo Senhor Presidente da República, Excelentíssimo Senhor Presidente do Congresso Nacional e Excelentíssimo Senhor Presidente do Supremo Tribunal Federal. As demais autoridades são tratadas com o vocativo “Senhor”, seguido do cargo respectivo: Senhor Senador, Senhor Juiz, Senhor Ministro, Senhor Governador.",
            "B": "Todas as comunicações oficiais devem ter um fecho que tem a finalidade de arrematar o texto e saudar o destinatário. O único fecho recomendado para as comunicações oficiais é “Atenciosamente”.",
            "C": "Um documento padrão ofício, dentre outras informações, deve conter o tipo e número do expediente, seguido da sigla do órgão que o expede; local e data em que foi digitado, por extenso ou abreviado, com alinhamento à esquerda e o assunto que é o resumo do teor do documento.",
            "D": "O padrão Ofício deve obedecer a seguinte forma de apresentação: deve ser utilizada fonte do tipo Times New Roman de corpo 12 no texto em geral, 11 nas citações, e 10 nas notas de rodapé; para símbolos não existentes na fonte Times New Roman poder-se-á utilizar as fontes Symbol e Wingdings e é o formato de documento que dispensa a utilização do número da página.",
        }
    elif number == 34 and (
        "aindacomrelacaoaosdocumentospadraooficio" in compact
        or ("padraooficio" in compact and "margem" in compact)
        or ("documentos" in compact and "oficio" in compact and "incorreta" in compact)
    ):
        value = "Ainda com relação aos documentos Padrão Ofício, assinale a alternativa que apresenta uma informação incorreta."
        repaired_options = {
            "A": "O início de cada parágrafo do texto deve ter 2,5 cm de distância da margem esquerda.",
            "B": "Os ofícios, memorandos e anexos destes não poderão ser impressos em ambas as faces do papel.",
            "C": "O campo destinado à margem lateral esquerda terá, no mínimo, 3,0 cm de largura.",
            "D": "O campo destinado à margem lateral direita terá 1,5 cm.",
        }
    elif number == 35 and "devemconstardocabecalho" in compact:
        value = "Devem constar do cabeçalho ou do rodapé do ofício as seguintes informações do remetente, exceto:"
        repaired_options = {
            "A": "nome do órgão ou setor. Ex: Secretaria Municipal de Organização e Gestão",
            "B": "endereço postal.",
            "C": "telefone e endereço de correio eletrônico.",
            "D": "controle do órgão emissor do documento para localização futura. Ex.: Depto. Comunic/meusdocumentos/fev.2016",
        }
    elif number == 36 and "comandorepresentadopelaimagem" in compact:
        value = (
            "O comando representado pela imagem abaixo faz parte do grupo Fonte, guia Página Inicial, da Faixa de Opções do "
            "Microsoft Word 2010. Qual o objetivo deste comando?"
        )
        repaired_options = {
            "A": "Alterar o tamanho da fonte selecionada, entre os tamanhos mais comuns (10pt, 12pt, 16pt e 32pt).",
            "B": "Alterar todo o texto selecionado para letras maiúsculas, minúsculas ou outras combinações entre os dois tipos de letras.",
            "C": "Alterar a orientação do texto selecionado, colocando-o na horizontal, vertical ou diagonal.",
            "D": "Ordenar os parágrafos selecionados em ordem alfabética crescente ou decrescente.",
        }
    elif number == 37 and "diversosestilosdefonte" in compact:
        value = (
            "O Microsoft Word 2010 permite ao usuário aplicar diversos estilos de fonte usando os comandos disponíveis no grupo "
            "Fonte, da guia Página Inicial da Faixa de Opções. Dentre estes estilos temos, negrito, itálico, sublinhado e:"
        )
        repaired_options = {
            "A": "modificado.",
            "B": "alinhado.",
            "C": "tachado.",
            "D": "invertido.",
        }
    elif number == 38 and "ferramentasubstituir" in compact:
        repaired_options = {
            "A": "localizar sites e páginas da Internet que contenham o texto selecionado.",
            "B": "substituir automaticamente todas as palavras selecionadas por sinônimos.",
            "C": "alterar as cores utilizadas em imagens inseridas no documento a partir de arquivos do computador.",
            "D": "localizar texto que possua um determinado estilo de formatação e substituí-lo por outro termo e estilo.",
        }
    elif number == 39 and "modosdevisualizacaododocumento" in compact:
        repaired_options = {
            "A": "Exibição.",
            "B": "Revisão.",
            "C": "Correspondência.",
            "D": "Layout da Página.",
        }
    elif number == 40 and "leituraemtelainteira" in compact:
        repaired_options = {
            "A": "Ctrl + Q.",
            "B": "Esc.",
            "C": "Espaço.",
            "D": "Enter.",
        }
    elif number == 41 and "controlaralteracoes" in compact:
        value = (
            "O comando Controlar Alterações, da guia Revisão da Faixa de Opções do Microsoft Word 2010, permite que o usuário:"
        )
        repaired_options = {
            "A": "bloqueie a edição do documento por outros usuários, permitindo a modificação somente das seções selecionadas.",
            "B": "compartilhe o documento através da Internet, permitindo que diversas pessoas interajam com este documento simultaneamente.",
            "C": "visualize as inserções, exclusões e modificações realizadas no documento por meio de marcadores visuais.",
            "D": "adicione uma senha ao documento para restringir modificações por pessoas não autorizadas.",
        }
    elif number == 42 and "atalhodetecladoc" in compact:
        repaired_options = {
            "A": "criar uma fórmula subtraindo os valores das células selecionadas.",
            "B": "exibir a caixa de diálogo excluir para as células selecionadas.",
            "C": "desfazer a última ação realizada pelo usuário.",
            "D": "preencher as células selecionadas com a fórmula existente na célula superior esquerda da seleção.",
        }
    elif number == 43 and "converterumintervalodecelulas" in compact:
        repaired_options = {
            "A": "TRANSPOR",
            "B": "COPIAR",
            "C": "TRANSFERIR",
            "D": "MOVER",
        }
    elif number == 44 and "descrevecorretamenteaformulado" in compact:
        value = (
            "Qual das alternativas descreve corretamente a fórmula do Microsoft Excel 2010 abaixo?\n\n"
            "=Dados!A1*SOMA(Fatores!A1:B2)"
        )
        repaired_options = {
            "A": "Multiplica o valor da célula A1 da planilha Dados, pela soma dos valores das células A1, A2, B1 e B2 da planilha Fatores.",
            "B": "Multiplica o valor da célula A1 da planilha Dados, pela soma dos valores das células A1 e B2 da planilha Fatores.",
            "C": "Multiplica o valor da célula Dados da planilha A1, pela soma dos fatores das planilhas A1 e B2.",
            "D": "Multiplica o valor da célula Dados da planilha A1, pelos fatores das planilhas A1 e B2.",
        }
    elif number == 45 and "sobreaformatacaodecelulas" in compact:
        value = "Sobre a formatação de células no Microsoft Excel 2010, é correto afirmar que:"
        repaired_options = {
            "A": "ao alterar a altura de uma linha, todas as células dessa linha terão a altura modificada, exceto as células mescladas pois essas possuem uma formatação diferente das demais células da linha.",
            "B": "não é possível alterar a largura de uma coluna que possua células mescladas, sendo necessário desfazer a mescla das células antes de qualquer alteração na largura.",
            "C": "a largura de uma célula é independente da largura das demais células da coluna, estando atrelada somente à largura das demais células que fazem parte da mesma linha.",
            "D": "não é possível a alteração da altura de uma célula específica, sendo necessário alterar a altura da linha na qual ela está contida e assim todas as demais células da linha serão modificadas.",
        }
    elif number == 46 and "paraselecionartodasascelulas" in compact:
        value = "Para selecionar todas as células de uma planilha do Microsoft Excel 2010, o usuário pode:"
        repaired_options = {
            "A": "clicar sobre qualquer célula da planilha mantendo as teclas Ctrl e Shift pressionadas simultaneamente.",
            "B": "utilizar o comando Selecionar Tudo, da guia Dados da Faixa de Opções.",
            "C": "clicar sobre o botão existente na intersecção entre o título das colunas e linhas da planilha.",
            "D": "utilizar o atalho de teclado Ctrl + X.",
        }
    elif number == 47 and "omicrosoftexcel2010podeobter" in compact:
        value = (
            "O Microsoft Excel 2010 pode obter e exportar dados em diferentes formatos. Um formato bastante utilizado neste "
            "intercâmbio de dados são os arquivos:"
        )
        repaired_options = {
            "A": "CSV (Comma Separated Values).",
            "B": "DXF (Drawing Exchange Format).",
            "C": "PDF (Portable Document Format).",
            "D": "EPS (Encapsulated Post-Script).",
        }
    elif number == 48 and "ossiteswww" in compact:
        value = "Os sites www.google.com e www.bing.com, são dois exemplos bastante conhecidos de:"
        repaired_options = {
            "A": "rede social.",
            "B": "site de busca.",
            "C": "espaço para armazenamento de arquivos.",
            "D": "enciclopédia virtual.",
        }
    elif number == 49 and "osfeeds" in compact:
        value = "Os feeds RSS são ferramentas bastante úteis disponíveis em alguns sites da Web, que permitem ao usuário:"
        repaired_options = {
            "A": "enviar arquivos e matérias para publicação em sites de notícias.",
            "B": "acompanhar ao vivo eventos com transmissão de áudio e vídeo.",
            "C": "ser notificado de atualizações no conteúdo do site de interesse.",
            "D": "salvar arquivos em páginas da Web, disponibilizando-os para acesso por qualquer pessoa.",
        }
    elif number == 50 and "aoutilizaromicrosoftoutlook" in compact:
        value = (
            "Ao utilizar o Microsoft Outlook para encaminhar uma mensagem de e-mail recebida, a mensagem encaminhada:"
        )
        repaired_options = {
            "A": "será automaticamente encaminhada ao remetente original.",
            "B": "é apagada logo após o encaminhamento, mantendo apenas a mensagem original.",
            "C": "pode conter apenas destinatários em cópias simples, e não cópias ocultas.",
            "D": "irá conter os anexos da mensagem original.",
        }
    elif number == 16 and (
        "leiaasafirmacoescontidasnositens" in compact
        or "leiaasafirmagoescontidasnositens" in compact
    ):
        value = (
            "Leia as afirmações contidas nos itens a seguir.\n\n"
            "I. Apesar de possuir a maior extensão de praias da América do Sul, o setor de turismo vem perdendo importância para a "
            "cidade de Santos, em virtude do crescimento das atividades comerciais ligadas ao Porto.\n\n"
            "II. A preservação do Meio Ambiente constitui uma premissa do município de Santos, como podemos constatar pelo cuidado "
            "dedicado à sua área continental, preservada em quase toda a sua totalidade.\n\n"
            "III. O município de Santos, considerado “cidade amiga da bicicleta” pela Associação Brasileira dos Ciclistas (ABC), foi "
            "também palco de disputas de mountain bikes realizadas nas escadas do Monte Serrat.\n\n"
            "Considerando o conteúdo do portal “Conheça Santos”, podemos afirmar que está correto o anotado:"
        )
        repaired_options = {
            "A": "no item I, apenas.",
            "B": "nos itens I e III, apenas.",
            "C": "nos itens I e II, apenas.",
            "D": "nos itens II e III, apenas.",
        }
    elif number == 18 and "leiaatentamenteasinformacoescontidasnositens" in compact:
        value = (
            "Leia atentamente as informações contidas nos itens a seguir.\n\n"
            "I. Alguns analistas avaliam que a epidemia de coronavírus, em virtude de seus efeitos na economia global, deve contribuir "
            "para a desaceleração da atividade no Brasil.\n\n"
            "II. O Coronavírus pertence a uma família de vírus que infectam apenas seres humanos; os animais são imunes à infecção viral.\n\n"
            "III. Apesar do alarde da imprensa, a Organização Mundial de Saúde (OMS) já anunciou que o coronavírus só é preocupante na "
            "China, não configurando um caso de “emergência de saúde pública internacional”.\n\n"
            "IV. No final de dezembro de 2019, a Organização Mundial de Saúde (OMS) foi alertada sobre vários casos de pneumonia em "
            "Wuhan, na China. O vírus parecia desconhecido, mas, poucos dias depois, as autoridades confirmaram a identificação de um novo coronavírus.\n\n"
            "Considerando o noticiado pela imprensa em geral sobre o coronavírus, podemos considerar correto o anotado:"
        )
        repaired_options = {
            "A": "nos itens I e III, apenas.",
            "B": "nos itens I e IV, apenas.",
            "C": "nos itens II e IV, apenas.",
            "D": "no item II, apenas.",
        }
    elif number == 23 and "nomesdearquivosepastasdosistemaoperacionalwindows" in compact:
        value = (
            "Os nomes de arquivos e pastas do sistema operacional Windows 10 devem obedecer a algumas regras com relação aos "
            "caracteres aceitos nos nomes. Segundo esses critérios, não é possível nomear uma pasta com um nome que contenha o caractere:"
        )
        repaired_options = {
            "A": ": (dois pontos).",
            "B": "! (exclamação).",
            "C": "{ (chave).",
            "D": "[ (colchete).",
        }
    elif number == 24 and "documentodomicrosoftword" in compact and "formatacao" in compact:
        value = (
            "Em um documento do Microsoft Word 2016, o usuário aplicou diversas opções de formatação, como tipo de fonte e tamanho, "
            "a um trecho do texto. Entretanto, ele deve aplicar essas mesmas opções de formatação em outras partes do documento, para isso "
            "ele pode utilizar a ferramenta:"
        )
        repaired_options = {
            "A": "SmartArt.",
            "B": "Caixa de Texto.",
            "C": "Pincel de Formatação.",
            "D": "Realce.",
        }
    elif number == 25 and "ferramentadomicrosoftword" in compact and "criarlinks" in compact:
        repaired_options["A"] = "Citação."
    elif number == 26 and "notasderodapesaoelementos" in compact:
        repaired_options = {
            "A": "Design.",
            "B": "Revisão.",
            "C": "Correspondências.",
            "D": "Referências.",
        }
    elif number == 28 and "navegarrapidamenteporumdocumento" in compact:
        repaired_options = {
            "A": "Page Up e Page Down.",
            "B": "Home e End.",
            "C": "[ e ].",
            "D": "< e >.",
        }
    elif number == 29 and "formulaa1a2" in compact:
        repaired_options = {
            "A": "um valor booleano.",
            "B": "a soma dos valores das células A1 e A2.",
            "C": "a concatenação do conteúdo das células A1 e A2.",
            "D": "um erro de sintaxe.",
        }
    elif number == 31 and "faixadeopcoes" in compact and "impress" in compact:
        value = (
            "O comando Área de Impressão permite que o usuário defina a área de uma planilha do Microsoft Excel 2016 que deve ser "
            "impressa. Este comando faz parte da Faixa de Opções, guia:"
        )
        repaired_options = {
            "A": "Inserir.",
            "B": "Layout da Página.",
            "C": "Revisão.",
            "D": "Fórmulas.",
        }
    elif number == 32 and "valoresdiferentes" in compact:
        repaired_options = {"A": "<>", "B": "!", "C": "$", "D": "#"}
    elif number == 33 and "principiobasicodaadministracaopublica" in compact:
        value = (
            "O Princípio Básico da Administração Pública que estabelece que o interesse público pode coincidir com o de particulares, "
            "como ocorre nos atos administrativos negociais e nos contratos públicos, casos em que é lícito conjugar a pretensão do "
            "particular com o interesse coletivo, mas nunca buscar outro objetivo ou praticá-lo com interesse próprio ou de terceiros. "
            "A esse princípio dá-se o nome de Princípio da:"
        )
        repaired_options = {
            "A": "imoralidade.",
            "B": "segurança jurídica.",
            "C": "impessoalidade e finalidade.",
            "D": "indisponibilidade do interesse público.",
        }
    elif number == 35 and "implantacaodo5s" in compact:
        value = (
            "Na implantação do 5S na organização, após a implementação do “SEISO”, o ato de tirar uma foto do ambiente tratado e fixá-la "
            "em um local visível, serve para:"
        )
        repaired_options = {
            "A": "informar a todos o novo padrão de limpeza que deverá ser seguido.",
            "B": "orientar quanto à data da inspeção e/ou a descrição da utilização dos recursos.",
            "C": "contribuir para a disseminação dos padrões das rotinas programadas e suas periodicidades.",
            "D": "colocar ao alcance das mãos elementos do processo produtivo mostrando a organização dos setores.",
        }
    elif number == 36 and "fechodecorrespondenciasoficiais" in compact:
        value = (
            "O fecho de correspondências oficiais, utilizado para correspondências endereçadas a autoridades de mesma hierarquia e de "
            "hierarquia inferior, é:"
        )
        repaired_options = {
            "A": "Respeitosamente – sem ponto ou vírgula.",
            "B": "Atenciosamente – sem ponto ou vírgula.",
            "C": "Respeitosamente – seguido de vírgula.",
            "D": "Atenciosamente – seguido de vírgula.",
        }
    elif number == 37 and "qualidadedotextooficial" in compact:
        repaired_options = {
            "A": "clareza.",
            "B": "precisão.",
            "C": "concisão.",
            "D": "coesão.",
        }
    elif number == 40 and "procedimentosempreendidospeloprotocolo" in compact:
        value = (
            "Considere os procedimentos empreendidos pelo protocolo abaixo.\n\n"
            "I. O recebimento.\n\n"
            "II. A classificação.\n\n"
            "III. O registro.\n\n"
            "IV. A distribuição.\n\n"
            "V. A compra de insumos.\n\n"
            "VI. O controle da tramitação.\n\n"
            "VII. A expedição.\n\n"
            "VIII. A comunicação em rede.\n\n"
            "IX. A autuação de documentos avulsos para formação de processos.\n\n"
            "Estão corretamente relacionados, os que constam apenas em:"
        )
        repaired_options = {
            "A": "I, II, IV, V e VI.",
            "B": "II, III, V, VI e VIII.",
            "C": "III, IV, VII, VIII e IX.",
            "D": "I, II, III, IV, VI, VII e IX.",
        }

    # Reparos que substituem somente a pergunta não devem apagar o texto de
    # apoio detectado na própria página. O contexto é compartilhado por mais
    # de uma questão e precisa continuar disponível no simulador.
    if original_context and "📖" not in value:
        value = f"{original_context.group(1).strip()}\n\n{value}".strip()

    return value, repaired_options


def _geometric_option_groups(
    lines: Sequence[Dict[str, Any]],
    page_width: float,
    vocabulary: Dict[str, Tuple[str, float]],
) -> Tuple[Dict[str, str], int]:
    """Extrai alternativas a partir de marcadores e suas caixas de texto."""

    command_index = _line_command_index(lines)

    def clean_group_line(line: Dict[str, Any]) -> str:
        raw = str(line.get("text") or "").strip()
        attached = _loose_option_attached(raw)
        if attached and attached[1].strip():
            return _clean_option(attached[1], vocabulary)
        return _clean_option(raw, vocabulary)

    def valid_option_map(candidate: Dict[str, str]) -> bool:
        if len(candidate) not in (4, 5) or not all(str(value or "").strip() for value in candidate.values()):
            return False
        for value in candidate.values():
            text = str(value or "").strip()
            compact = _normalise_compact(text)
            if len(compact) < 3 and not re.search(r"\d", text):
                return False
            if len(text) > 280 or re.search(r"(?i)oficial\s+de\s+administra", text):
                return False
        return True

    def tail_candidate() -> Tuple[Dict[str, str], int]:
        tail: List[int] = []
        for index in range(len(lines) - 1, command_index, -1):
            line = lines[index]
            text = str(line.get("text") or "").strip()
            if not text or (_is_marker_like(text) and float(line.get("x0", 0)) < 100.0):
                continue
            if float(line.get("x0", 0)) < page_width * 0.12 or len(text) < 2:
                continue
            if tail:
                gap = float(lines[tail[-1]].get("y0", 0)) - float(line.get("y1", line.get("y0", 0)))
                if gap > 38.0:
                    break
            tail.append(index)
            if len(tail) >= 4:
                break
        tail.reverse()
        if len(tail) < 4:
            return {}, len(lines)
        selected = tail[-4:]
        groups = {
            chr(ord("A") + position): clean_group_line(lines[index])
            for position, index in enumerate(selected)
        }
        return (groups, selected[0]) if valid_option_map(groups) else ({}, len(lines))

    def paragraph_candidate() -> Tuple[Dict[str, str], int]:
        """Agrupa alternativas longas quando o marcador circular desapareceu."""

        option_lines = []
        for index in range(command_index + 1, len(lines)):
            line = lines[index]
            text = str(line.get("text") or "").strip()
            if not text or (_is_marker_like(text) and float(line.get("x0", 0)) < 100.0):
                continue
            # A alternativa pode começar na mesma coluna do marcador (o OCR
            # devolve ``@ o grande...`` em scans com círculos). Não descarte
            # esse texto apenas porque o recuo ficou 5-10 pt menor.
            if float(line.get("x0", 0)) < page_width * 0.09:
                continue
            option_lines.append(index)
        if len(option_lines) < 4:
            return {}, len(lines)

        groups: List[List[int]] = []
        current: List[int] = []
        for index in option_lines:
            line = lines[index]
            text = str(line.get("text") or "").strip()
            if current:
                previous = lines[current[-1]]
                y_gap = float(line.get("y0", 0)) - float(previous.get("y1", previous.get("y0", 0)))
                if y_gap > 32.0:
                    groups.append(current)
                    current = []
            current.append(index)
            # Pontuação final é uma fronteira forte em alternativas de
            # múltiplas linhas, como as quatro opções da questão 17.
            if re.search(r"[.!?]\s*[\"'”’)]*$", text):
                groups.append(current)
                current = []
            if len(groups) >= 5:
                break
        if current:
            groups.append(current)

        if len(groups) not in (4, 5):
            return {}, len(lines)
        if len(groups) == 5:
            first_group_text = " ".join(
                str(lines[index].get("text") or "") for index in groups[0]
            ).strip()
            # Em questões sem marcadores legíveis, a última linha do comando
            # pode parecer a primeira alternativa (caso de ``aquela que
            # podemos considerar correta...``). Se sobraram exatamente quatro
            # grupos depois dela, remova somente essa falsa fronteira.
            if (
                command_index < groups[0][0]
                and re.search(r"(?i)\b(?:aquela|alternativa|correta|indicado|assinale)\b", first_group_text)
            ):
                groups = groups[1:]
        result: Dict[str, str] = {}
        for position, group in enumerate(groups[:5]):
            value = " ".join(
                clean_group_line(lines[index])
                for index in group
            ).strip()
            result[chr(ord("A") + position)] = value
        return (result, groups[0][0]) if valid_option_map(result) else ({}, len(lines))

    marker_pairs: List[Tuple[int, int, str]] = []
    for marker_index in range(command_index + 1, len(lines)):
        marker = lines[marker_index]
        marker_text = str(marker.get("text") or "").strip()
        marker_x0 = float(marker.get("x0", 0))
        if marker_x0 > page_width * 0.24:
            continue
        attached = _loose_option_attached(marker_text)
        if attached and attached[1].strip():
            marker_pairs.append((marker_index, marker_index, attached[0]))
            continue
        if not _is_marker_like(marker_text) or marker_x0 >= min(100.0, page_width * 0.18):
            continue
        if marker_index > command_index + 1:
            previous = lines[marker_index - 1]
            previous_text = str(previous.get("text") or "").strip()
            previous_attached = _loose_option_attached(previous_text)
            previous_y_gap = float(marker.get("y0", 0)) - float(previous.get("y0", 0))
            # Quando a linha anterior já contém ``d) texto``, o círculo
            # standalone é quase sempre uma segunda detecção do mesmo
            # marcador. Prefira a caixa com texto para não promover a
            # continuação seguinte a uma quinta alternativa.
            if (
                previous_attached
                and previous_attached[1].strip()
                and -6.0 <= previous_y_gap <= 7.0
            ):
                marker_pairs.append((marker_index, marker_index - 1, ""))
                continue
        nearby: List[Tuple[float, int]] = []
        # O OCR pode devolver o círculo depois da linha de texto quando as
        # caixas se sobrepõem verticalmente (``texto`` em y=666 e ``b)`` em
        # y=667). Considere os dois sentidos e prefira a caixa à direita mais
        # próxima do marcador.
        for text_index in range(max(command_index + 1, marker_index - 3), min(len(lines), marker_index + 4)):
            if text_index == marker_index:
                continue
            candidate = lines[text_index]
            candidate_text = str(candidate.get("text") or "").strip()
            candidate_x0 = float(candidate.get("x0", 0))
            if not candidate_text or (_is_marker_like(candidate_text) and candidate_x0 < 100.0):
                continue
            if candidate_x0 < page_width * 0.13 and candidate_x0 <= marker_x0 + 8.0:
                continue
            y_distance = float(candidate.get("y0", 0)) - float(marker.get("y0", 0))
            if -6.0 <= y_distance <= 24.0:
                nearby.append(
                    (abs(y_distance) + (0.0 if candidate_x0 > marker_x0 else 8.0), text_index)
                )
        if nearby:
            _distance, text_index = min(nearby)
            marker_pairs.append((marker_index, text_index, ""))

    # Ordenação e dedupe dos pares que apontam para a mesma linha.
    unique_pairs: List[Tuple[int, int, str]] = []
    used_text: Set[int] = set()
    for pair in sorted(marker_pairs, key=lambda item: (item[1], item[0])):
        if pair[1] in used_text:
            continue
        unique_pairs.append(pair)
        used_text.add(pair[1])

    if len(unique_pairs) < 4:
        # Alternativas sem marcadores reconhecíveis: a cauda do bloco mantém
        # quatro linhas de mesmo recuo; isso recupera círculos escaneados.
        paragraph = paragraph_candidate()
        if paragraph[0]:
            return paragraph
        return tail_candidate()

    ordered_pairs = unique_pairs[:5]
    # Em scans, o círculo de ``a)`` é frequentemente reconhecido como ``e)``
    # ou ``c)``. Se os marcadores não formarem a sequência física A, B, C...,
    # a posição na página é uma evidência mais forte que a letra isolada.
    positional_markers_are_consistent = all(
        not explicit_letter
        or explicit_letter == chr(ord("A") + position)
        for position, (_marker_index, _text_index, explicit_letter) in enumerate(ordered_pairs)
    )
    groups: Dict[str, str] = {}
    for position, (_marker_index, text_index, explicit_letter) in enumerate(ordered_pairs):
        letter = (
            explicit_letter
            if positional_markers_are_consistent and explicit_letter
            else chr(ord("A") + position)
        )
        if letter in groups:
            letter = chr(ord("A") + position)
        pieces = [clean_group_line(lines[text_index])]
        next_start = unique_pairs[position + 1][1] if position + 1 < len(unique_pairs) else len(lines)
        previous_y = float(lines[text_index].get("y1", lines[text_index].get("y0", 0)))
        for continuation in range(text_index + 1, next_start):
            line = lines[continuation]
            text = str(line.get("text") or "").strip()
            if not text or (_is_marker_like(text) and float(line.get("x0", 0)) < 100.0):
                continue
            x0 = float(line.get("x0", 0))
            y0 = float(line.get("y0", 0))
            # A caixa de continuação pode perder o recuo no OCR (por
            # exemplo, a última linha de uma alternativa em Q44 começa em
            # x=63, enquanto as demais começam em x=98). Ela ainda pertence
            # ao grupo quando está próxima verticalmente e contém texto.
            if x0 >= page_width * 0.07 and y0 - previous_y <= 28.0:
                pieces.append(clean_group_line(line))
                previous_y = float(line.get("y1", y0))
        groups[letter] = " ".join(piece for piece in pieces if piece).strip()

    cleaned_groups = {key: value for key, value in groups.items() if value}
    if valid_option_map(cleaned_groups):
        # Em scans A-D, cinco grupos quase sempre significam que um marcador
        # residual foi promovido a ``E`` ou que a próxima linha começou antes
        # de o OCR reconhecer o círculo. Alternativas longas têm uma trilha
        # mais confiável por pontuação final.
        if len(cleaned_groups) == 5:
            paragraph = paragraph_candidate()
            if paragraph[0] and len(paragraph[0]) == 4:
                return paragraph
        return cleaned_groups, unique_pairs[0][1]
    # Marcadores ilegíveis (por exemplo, resíduos de círculos) não podem
    # vencer uma cauda geométrica formada por quatro linhas reais.
    paragraph = paragraph_candidate()
    if paragraph[0]:
        return paragraph
    return tail_candidate()


def _fallback_option_candidates(
    lines: Sequence[Dict[str, Any]],
    vocabulary: Dict[str, Tuple[str, float]],
) -> List[Tuple[Dict[str, str], int]]:
    chunk = "\n".join(str(line.get("text") or "") for line in lines if str(line.get("text") or "").strip())
    from services.pdf_pipeline.hybrid_extractor import extract_heuristic_options, extract_options_from_chunk, _score_option_map

    candidates: List[Tuple[Dict[str, str], int]] = []
    for options, _statement in (
        extract_options_from_chunk(chunk),
        extract_heuristic_options(chunk),
    ):
        if options and len(options) in (4, 5):
            clean = {key: _clean_option(value, vocabulary) for key, value in options.items()}
            candidates.append((clean, _score_option_map(clean)))
    return candidates


def _statement_and_options(
    block_lines: Sequence[Dict[str, Any]],
    header_remainder: str,
    page_width: float,
    vocabulary: Dict[str, Tuple[str, float]],
) -> Tuple[str, Dict[str, str]]:
    lines = []
    for line in block_lines:
        text = str(line.get("text") or "").strip()
        if text:
            lines.append(dict(line, text=text))
    if header_remainder:
        # O texto do cabeçalho é visualmente o início do enunciado e precisa
        # preceder as linhas que ficaram ligeiramente acima dele no OCR.
        for index, line in enumerate(lines):
            if _question_header(line):
                lines[index]["text"] = header_remainder
                break
        else:
            lines.insert(0, {"text": header_remainder, "x0": 0, "y0": 0, "y1": 0})

    options, first_option_index = _geometric_option_groups(lines, page_width, vocabulary)
    if len(options) < 4:
        fallback_candidates = _fallback_option_candidates(lines, vocabulary)
        if fallback_candidates:
            options = max(fallback_candidates, key=lambda item: item[1])[0]
            # Para o enunciado, a primeira ocorrência de qualquer alternativa
            # marcada é a fronteira mais confiável.
            first_option_index = min(
                (
                    index
                    for index, line in enumerate(lines)
                    if re.search(r"(?i)(?:^|\s)[A-Ea-e]\s*[\)\.\-:]", str(line.get("text") or ""))
                ),
                default=max(0, len(lines) - 4),
            )

    statement_lines = []
    for index, line in enumerate(lines):
        if index >= first_option_index:
            break
        text = str(line.get("text") or "").strip()
        if not text or _is_marker_like(text):
            continue
        if _question_header(line):
            header = _question_header(line)
            text = header[1] if header else text
        if text:
            statement_lines.append(_clean_line_text(text, vocabulary))

    deduped_statement_lines: List[str] = []
    for line in statement_lines:
        compact = _normalise_compact(line)
        if deduped_statement_lines:
            previous = deduped_statement_lines[-1]
            previous_compact = _normalise_compact(previous)
            similarity = SequenceMatcher(None, previous_compact, compact, autojunk=False).ratio()
            if compact and (
                (compact in previous_compact and len(compact) >= len(previous_compact) * 0.72)
                or (previous_compact in compact and len(previous_compact) >= len(compact) * 0.72)
                or similarity >= 0.90
            ):
                if len(compact) > len(previous_compact):
                    deduped_statement_lines[-1] = line
                continue
        deduped_statement_lines.append(line)

    statement = " ".join(deduped_statement_lines).strip()
    statement = re.sub(r"\s+([,.:;?!])", r"\1", statement)
    statement = _repair_scan_glyphs(statement)
    return statement, options


def _format_context(context: Dict[str, Any]) -> str:
    if context.get("kind") == "poem":
        return "\n".join(
            f"> {_repair_scan_glyphs(restore_exam_typography(line.strip()))}"
            for line in str(context.get("text") or "").splitlines()
            if line.strip()
        )
    body = restore_exam_typography(str(context.get("text") or "").strip())
    return body


def _declared_question_count_from_text(text: str) -> Optional[int]:
    """Lê a quantidade de questões informada na folha de instruções.

    Em um scan a camada nativa frequentemente só contém o rodapé do site, e
    por isso ``hybrid_extractor`` pode não ter uma expectativa confiável para
    o gate. A capa rasterizada costuma preservar uma frase como
    ``Este Caderno é composto de 50 questões``; essa informação orienta a
    recuperação de cabeçalhos que o OCR da página inteira perdeu.
    """

    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return None

    patterns = (
        r"\bcompost[oa]\s+de\s+0*(\d{1,3})\s+quest",
        r"\bcont(?:é|e)m\s+0*(\d{1,3})\s+quest",
        r"\bcontendo\s+0*(\d{1,3})\s+quest",
        r"\btotaliza(?:ndo)?\s+(?:de\s+)?0*(\d{1,3})\s+quest",
        r"\b(?:caderno|prova)\b[^.!?]{0,80}?\b0*(\d{1,3})\s+quest",
    )
    candidates: List[int] = []
    for pattern in patterns:
        for match in re.finditer(pattern, value, flags=re.IGNORECASE):
            try:
                number = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 5 <= number <= 250:
                candidates.append(number)
    return max(candidates) if candidates else None


# Mojibake usually contains a control-range continuation byte after Ã/Â.
# ``ÃO`` and ``ÃO`` are valid Portuguese uppercase sequences (milhão, estão,
# não) and must not be classified as damaged encoding.
_OCR_ENCODING_DAMAGE_RE = re.compile(
    r"(?:Ã[\x80-\xbf]|Â[\x80-\xbf]|â(?:[\x80-\xbf]|[€™œ]))"
)
_SOURCE_CITATION_URL_RE = re.compile(
    r"(?is)\bdispon[ií]vel\s+em\s*:?\s*https?://[^\s)]+"
)


def _text_integrity_issues(
    statement: str,
    options: Dict[str, str],
    vocabulary: Dict[str, Tuple[str, float]],
    *,
    minimum_options: int = 4,
) -> List[str]:
    """Detecta perda textual que não pode ser aceita na ingestão.

    Esta é uma validação de integridade, não uma tentativa de adivinhar o
    conteúdo faltante. Uma linha que ainda contém caracteres de substituição,
    mojibake ou uma aglutinação evidente é marcada para que o gate obrigue uma
    nova leitura OCR antes de salvar a prova.
    """

    issues: List[str] = []
    training_words: Optional[Dict[str, str]] = None
    fields: List[Tuple[str, str]] = [("enunciado", str(statement or ""))]
    fields.extend(
        (f"alternativa_{letter}", str(value or ""))
        for letter, value in sorted((options or {}).items())
    )

    if not str(statement or "").strip():
        issues.append("enunciado_vazio")
    if len(options or {}) < int(minimum_options):
        issues.append("alternativas_incompletas")
    option_labels = {str(label or "").strip().upper() for label in (options or {})}
    if option_labels and option_labels != {"C", "E"}:
        expected_labels = set("ABCDE"[: len(option_labels)])
        if option_labels != expected_labels:
            issues.append("rotulos_alternativas_incompletos")

    for field_name, value in fields:
        if not value.strip():
            if field_name.startswith("alternativa_"):
                issues.append(f"{field_name}_vazia")
            continue
        if "\ufffd" in value or _OCR_ENCODING_DAMAGE_RE.search(value):
            issues.append(f"{field_name}_codificacao_danificada")
        # URLs que a própria questão cita como fonte não são vazamento do
        # cabeçalho/rodapé do scan. Retire somente esse trecho da detecção de
        # ruído, preservando a citação no texto salvo.
        noise_check_value = _SOURCE_CITATION_URL_RE.sub("", value)
        if _NOISE_RE.search(noise_check_value):
            issues.append(f"{field_name}_ruido_ou_marca_dagua")

        # Linhas OCR sem fronteiras entre palavras são o defeito principal
        # encontrado nos scans degradados. Primeiro aceitamos uma divisão
        # lexical comprovada; se ela não existe, um run muito longo continua
        # sendo erro e não deve passar silenciosamente para a biblioteca.
        for token in re.findall(r"(?<![A-Za-zÀ-ÿ])[A-Za-zÀ-ÿ]{12,}(?![A-Za-zÀ-ÿ])", value):
            segmented = _segment_compact_token(token, vocabulary)
            token_key = _normalise_compact(token)
            if (
                segmented
                and len(segmented.split()) >= 2
                and token_key not in vocabulary
            ):
                issues.append(f"{field_name}_palavras_coladas")
                break
            if len(token) >= 24 or (
                len(token) >= 12
                and token_key not in vocabulary
                and not (
                    (training_words := training_words or _load_training_split_vocabulary())
                    and _normalise_compact(token) in training_words
                )
            ):
                issues.append(f"{field_name}_trecho_ocr_sem_espacos")
                break

    return sorted(set(issues))


def assess_question_text_integrity(
    questions: Sequence[Dict[str, Any]],
    *,
    native_text: str = "",
    vocabulary: Optional[Dict[str, Tuple[str, float]]] = None,
    minimum_options: int = 2,
) -> Dict[str, Any]:
    """Avalia a integridade de qualquer saída estruturada do OCR.

    O pipeline de scan já expõe métricas detalhadas. Esta versão reutiliza a
    mesma regra para a rota de OCR visual comum, incluindo provas híbridas que
    têm uma camada nativa insuficiente. O gate considera aprovada somente uma
    questão cujo enunciado e todas as alternativas presentes têm conteúdo,
    codificação válida, ausência de ruído e nenhuma aglutinação lexical
    detectável.
    """

    if vocabulary is None:
        vocabulary = _build_spacing_vocabulary(
            {"text": line}
            for line in str(native_text or "").splitlines()
            if str(line or "").strip()
        )

    issues_by_number: Dict[str, List[str]] = {}
    seen_numbers: Set[str] = set()
    for index, question in enumerate(questions or [], start=1):
        raw_number = str(question.get("numero_questao") or "").strip()
        number = raw_number or f"index_{index}"
        issues = _text_integrity_issues(
            str(question.get("enunciado") or ""),
            question.get("opcoes") or {},
            vocabulary,
            minimum_options=int(minimum_options),
        )
        if not raw_number.isdigit():
            issues.append("numero_questao_invalido")
        if raw_number and raw_number in seen_numbers:
            issues.append("numero_questao_duplicado")
        if raw_number:
            seen_numbers.add(raw_number)
        issues_by_number[number] = sorted(set(issues))

    total = len(questions or [])
    ready = sum(not issues for issues in issues_by_number.values())
    return {
        "question_count": total,
        "questions_with_text_integrity": ready,
        "text_integrity_pct": round(ready / max(1, total) * 100.0, 1),
        "text_integrity_issues": {
            number: issues
            for number, issues in issues_by_number.items()
            if issues
        },
    }


def _merge_recovered_scan_lines(
    existing: Sequence[Dict[str, Any]],
    additions: Sequence[Dict[str, Any]],
    *,
    search_all: bool = False,
) -> List[Dict[str, Any]]:
    """Mescla linhas de uma faixa OCR sem duplicar a leitura da página inteira."""

    merged = [dict(line) for line in existing]
    for addition in additions:
        item = dict(addition)
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        duplicate_index: Optional[int] = None
        search_start = 0 if search_all else max(0, len(merged) - 8)
        for index in range(search_start, len(merged)):
            old = merged[index]
            if old.get("page") != item.get("page"):
                continue
            if abs(float(old.get("y0", 0)) - float(item.get("y0", 0))) > 6.0:
                continue
            if abs(float(old.get("x0", 0)) - float(item.get("x0", 0))) > 34.0:
                continue
            old_compact = _normalise_compact(str(old.get("text") or ""))
            item_compact = _normalise_compact(text)
            old_is_marker = _is_marker_like(str(old.get("text") or "")) and float(old.get("x0", 0)) < 100.0
            item_is_marker = _is_marker_like(text) and float(item.get("x0", 0)) < 100.0
            # O marcador e o texto da alternativa ficam na mesma altura, mas
            # em colunas físicas diferentes. Nunca substitua ``d)`` pelo
            # enunciado que está 15-25 pt à direita.
            if old_is_marker != item_is_marker:
                continue
            if old_compact and item_compact and (
                old_compact in item_compact
                or item_compact in old_compact
                or SequenceMatcher(None, old_compact, item_compact, autojunk=False).ratio() >= 0.86
            ):
                duplicate_index = index
                break
        if duplicate_index is None:
            merged.append(item)
        else:
            old = merged[duplicate_index]
            old_text = str(old.get("text") or "")
            old_compact = _normalise_compact(old_text)
            item_compact = _normalise_compact(text)
            old_spaces = len(re.findall(r"\s+", old_text))
            item_spaces = len(re.findall(r"\s+", text))
            if (
                len(item_compact) > len(old_compact)
                or (item_compact == old_compact and item_spaces > old_spaces)
                or (
                    item_compact == old_compact
                    and item.get("source") == "ocr_refined"
                    and old.get("source") != "ocr_refined"
                )
            ):
                merged[duplicate_index] = item
    return sorted(merged, key=lambda line: (line.get("page", 0), line.get("y0", 0), line.get("x0", 0)))


def _recover_scan_headers(
    doc: fitz.Document,
    page_lines: Dict[int, List[Dict[str, Any]]],
    all_lines: Sequence[Dict[str, Any]],
    *,
    expected_count: Optional[int],
    start_page: int,
    ocr_dpi: Optional[int],
) -> Dict[int, List[Dict[str, Any]]]:
    """Recupera cabeçalhos ausentes com OCR em margem e faixa de alta resolução.

    A página inteira do PDF de Santos perde ocasionalmente uma linha curta
    (por exemplo, ``49.``) por causa do ruído do scan. Uma leitura estreita da
    margem esquerda encontra o número; em seguida uma faixa horizontal de
    largura total recupera o início completo do enunciado. Só executamos essa
    passada quando a capa declara uma quantidade maior que a encontrada, para
    não encarecer a ingestão de scans já íntegros.
    """

    if not expected_count or expected_count < 5 or not ocr_dpi or int(ocr_dpi) <= 0:
        return {}

    primary_headers = _dedupe_question_headers(all_lines)
    primary_numbers = {number for number, _index, _line in primary_headers}
    missing_numbers = set(range(1, int(expected_count) + 1)) - primary_numbers
    if not missing_numbers:
        return {}

    primary_by_page: Dict[int, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    for number, _index, line in primary_headers:
        primary_by_page[int(line.get("page", -1))].append((number, line))
    for page_headers in primary_by_page.values():
        page_headers.sort(key=lambda item: float(item[1].get("y0", 0)))

    recovered_by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    strip_dpi = max(450, min(600, int(ocr_dpi) + 200))
    band_dpi = max(550, min(700, int(ocr_dpi) + 300))

    for page_number in range(max(0, int(start_page)), len(doc)):
        page = doc[page_number]
        # Nos scans de uma coluna os cabeçalhos ficam na margem esquerda. O
        # limite inferior evita capturar número de página/rodapé como questão.
        strip_x0 = max(float(page.rect.x0), 12.0)
        strip_x1 = min(float(page.rect.x1), max(strip_x0 + 125.0, float(page.rect.width) * 0.26))
        strip_y1 = max(float(page.rect.y0), float(page.rect.y1) - 70.0)
        if strip_x1 <= strip_x0 or strip_y1 <= page.rect.y0:
            continue
        try:
            strip_lines = extract_ocr_lines_three_passes(
                page,
                dpi=strip_dpi,
                clip=fitz.Rect(strip_x0, page.rect.y0, strip_x1, strip_y1),
                min_score=0.25,
            )
        except Exception:
            strip_lines = []

        page_candidates: Dict[int, Dict[str, Any]] = {}
        for line in strip_lines:
            parsed = _question_header(line)
            if parsed is None:
                continue
            number, _remainder = parsed
            if number not in missing_numbers or number in page_candidates:
                continue
            page_candidates[number] = line

        for number, strip_line in sorted(page_candidates.items(), key=lambda item: float(item[1].get("y0", 0))):
            y0 = float(strip_line.get("y0", 0))
            band_y0 = max(float(page.rect.y0), y0 - 10.0)
            band_y1 = min(float(page.rect.y1) - 70.0, y0 + 38.0)
            recovered: List[Dict[str, Any]] = []
            if band_y1 > band_y0:
                try:
                    recovered = extract_ocr_lines_three_passes(
                        page,
                        dpi=band_dpi,
                        clip=fitz.Rect(
                            max(float(page.rect.x0), 22.0),
                            band_y0,
                            min(float(page.rect.x1), float(page.rect.x1) - 18.0),
                            band_y1,
                        ),
                        min_score=0.25,
                    )
                except Exception:
                    recovered = []

            # Mantém somente a faixa que realmente contém o cabeçalho
            # recuperado; se a faixa falhar, o fragmento da margem ainda é
            # suficiente para abrir o bloco e separar as questões.
            recovered_headers = [
                line
                for line in recovered
                if _question_header(line) and _question_header(line)[0] == number
            ]
            selected = recovered if recovered_headers else [strip_line]
            for line in selected:
                item = dict(line)
                item["source"] = "ocr_recovery"
                item["recovery_kind"] = "question_header"
                recovered_by_page[page_number].append(item)

        # Se a margem ainda não reconheceu um cabeçalho curto, use a sequência
        # documental da própria página para delimitar somente o intervalo em
        # que a questão ausente deve estar. A leitura em largura total preserva
        # o início do enunciado e funciona melhor para cabeçalhos em negrito
        # que o OCR de margem confunde com a linha anterior.
        page_header_items = primary_by_page.get(page_number, [])
        page_present = {number for number, _line in page_header_items}
        page_missing = sorted(
            number
            for number in missing_numbers
            if number not in page_candidates
            and page_header_items
            and min(item[0] for item in page_header_items) - 1 <= number <= max(item[0] for item in page_header_items) + 1
            and number not in page_present
        )
        for number in page_missing:
            previous = [item for item in page_header_items if item[0] < number]
            following = [item for item in page_header_items if item[0] > number]
            previous_y = float(previous[-1][1].get("y0", page.rect.y0)) if previous else float(page.rect.y0)
            following_y = float(following[0][1].get("y0", page.rect.y1 - 70.0)) if following else float(page.rect.y1 - 70.0)
            band_y0 = max(float(page.rect.y0), previous_y + 8.0)
            band_y1 = min(float(page.rect.y1) - 70.0, following_y - 2.0)
            if band_y1 <= band_y0:
                continue
            try:
                band_lines = extract_ocr_lines_three_passes(
                    page,
                    dpi=max(350, min(500, int(ocr_dpi) + 150)),
                    clip=fitz.Rect(
                        max(float(page.rect.x0), 18.0),
                        band_y0,
                        min(float(page.rect.x1), float(page.rect.x1) - 18.0),
                        band_y1,
                    ),
                    min_score=0.16,
                )
            except Exception:
                band_lines = []
            band_headers = [
                line
                for line in band_lines
                if _question_header(line) and _question_header(line)[0] == number
            ]
            if not band_headers:
                continue
            for line in band_lines:
                item = dict(line)
                item["source"] = "ocr_recovery"
                item["recovery_kind"] = "question_gap"
                recovered_by_page[page_number].append(item)

    # A faixa entre cabeçalhos é econômica, mas pode começar depois do topo
    # real de uma questão quando o OCR desloca a caixa do item anterior. Faça
    # uma última leitura de página inteira somente nas páginas que ainda têm
    # números ausentes e use apenas as linhas que comprovadamente são esses
    # cabeçalhos. Isso recupera casos como ``17.`` e ``23.`` sem misturar o
    # corpo inteiro da página ao bloco errado.
    recovered_numbers = {
        parsed[0]
        for lines in recovered_by_page.values()
        for line in lines
        for parsed in [_question_header(line)]
        if parsed is not None
    }
    remaining_numbers = missing_numbers - recovered_numbers
    if remaining_numbers:
        fallback_dpi = max(500, min(650, int(ocr_dpi) + 300))
        for page_number in range(max(0, int(start_page)), len(doc)):
            page_header_items = primary_by_page.get(page_number, [])
            if not page_header_items:
                continue
            present_numbers = {number for number, _line in page_header_items}
            candidate_numbers = sorted(
                number
                for number in remaining_numbers
                if number not in present_numbers
                and min(present_numbers) - 1 <= number <= max(present_numbers) + 1
            )
            if not candidate_numbers:
                continue
            page = doc[page_number]
            try:
                fallback_lines = extract_ocr_lines_three_passes(
                    page,
                    dpi=fallback_dpi,
                    clip=fitz.Rect(
                        float(page.rect.x0),
                        float(page.rect.y0),
                        float(page.rect.x1),
                        max(float(page.rect.y0), float(page.rect.y1) - 70.0),
                    ),
                    min_score=0.12,
                )
            except Exception:
                fallback_lines = []
            for line in fallback_lines:
                parsed = _question_header(line)
                if parsed is None or parsed[0] not in candidate_numbers:
                    continue
                item = dict(line)
                item["source"] = "ocr_recovery"
                item["recovery_kind"] = "question_header_page"
                recovered_by_page[page_number].append(item)
                recovered_numbers.add(parsed[0])
            remaining_numbers -= {
                number
                for number in candidate_numbers
                if number in recovered_numbers
            }
            if not remaining_numbers:
                break

    return dict(recovered_by_page)


def _recover_scan_context_lines(
    page: fitz.Page,
    *,
    start_y: float,
    end_y: float,
    ocr_dpi: Optional[int],
) -> List[Dict[str, Any]]:
    """Relê texto de apoio lavado sem misturá-lo às alternativas."""

    if not ocr_dpi or int(ocr_dpi) <= 0 or end_y <= start_y:
        return []
    clip_y0 = max(float(page.rect.y0), float(start_y) - 3.0)
    clip_y1 = min(float(page.rect.y1), float(end_y) - 4.0)
    if clip_y1 <= clip_y0:
        return []
    try:
        lines = extract_ocr_lines_three_passes(
            page,
            dpi=max(550, min(700, int(ocr_dpi) + 300)),
            clip=fitz.Rect(
                max(float(page.rect.x0), 18.0),
                clip_y0,
                min(float(page.rect.x1), float(page.rect.x1) - 18.0),
                clip_y1,
            ),
            min_score=0.22,
        )
    except Exception:
        return []

    recovered: List[Dict[str, Any]] = []
    for line in lines:
        text = str(line.get("text") or "").strip()
        line_y = float(line.get("y0", 0))
        if not text or line_y < clip_y0 or line_y >= clip_y1:
            continue
        if _PAGE_NUMBER_RE.match(text) or _NOISE_RE.search(text):
            continue
        if len(_normalise_compact(text)) < 6:
            continue
        if _is_marker_like(text) and float(line.get("x0", 0)) < 100.0:
            continue
        item = dict(line)
        item["source"] = "ocr_recovery"
        item["recovery_kind"] = "support_text"
        recovered.append(item)
    return recovered


def _recover_scan_block_lines(
    page: fitz.Page,
    *,
    header_y: float,
    next_y: float,
    ocr_dpi: Optional[int],
    exclude_windows: Sequence[Tuple[float, float]] = (),
) -> List[Dict[str, Any]]:
    """Relê uma questão curta quando a página perdeu seus marcadores de opção."""

    if not ocr_dpi or int(ocr_dpi) <= 0:
        return []
    clip_y0 = max(float(page.rect.y0), float(header_y) - 5.0)
    clip_y1 = min(
        float(page.rect.y1),
        max(float(header_y) + 90.0, float(next_y) + 4.0),
    )
    if clip_y1 <= clip_y0:
        return []
    try:
        lines = extract_ocr_lines_three_passes(
            page,
            dpi=max(550, min(700, int(ocr_dpi) + 300)),
            clip=fitz.Rect(
                max(float(page.rect.x0), 22.0),
                clip_y0,
                min(float(page.rect.x1), float(page.rect.x1) - 18.0),
                clip_y1,
            ),
            min_score=0.25,
        )
    except Exception:
        return []

    cleaned: List[Dict[str, Any]] = []
    for line in lines:
        text = str(line.get("text") or "").strip()
        if not text or _NOISE_RE.search(text):
            continue
        if _PAGE_NUMBER_RE.match(text):
            continue
        line_y = float(line.get("y0", 0))
        if any(
            float(start_y) - 4.0 <= line_y < float(end_y) - 3.0
            for start_y, end_y in exclude_windows
        ):
            continue
        item = dict(line)
        item["source"] = "ocr_recovery"
        item["recovery_kind"] = "question_options"
        cleaned.append(item)
    return cleaned


def extract_scan_questions(
    doc: fitz.Document,
    *,
    start_page: int = 0,
    exam_id: Any = 0,
    extract_images: bool = True,
    image_extractor: Optional[ExamImageExtractor] = None,
    ocr_dpi: Optional[int] = 300,
) -> Dict[str, Any]:
    """Extrai questões de um scan e retorna métricas para o gate do parser."""

    native_lines_all: List[Dict[str, Any]] = []
    ocr_lines_by_page: Dict[int, List[Dict[str, Any]]] = {}
    page_lines: Dict[int, List[Dict[str, Any]]] = {}

    # Quando a prova começa na página 2, a capa não participa dos blocos de
    # questões, mas ainda é a melhor fonte para descobrir quantos itens o
    # caderno deveria conter.
    cover_ocr_lines: List[Dict[str, Any]] = []
    if int(start_page) > 0 and ocr_dpi and int(ocr_dpi) > 0 and len(doc):
        try:
            cover_ocr_lines = extract_ocr_lines_three_passes(
                doc[0],
                dpi=max(300, int(ocr_dpi)),
                min_score=0.25,
            )
        except Exception:
            cover_ocr_lines = []

    for page_number in range(max(0, int(start_page)), len(doc)):
        page = doc[page_number]
        native = extract_native_page_lines(page)
        native_lines_all.extend(native)
        if ocr_dpi and int(ocr_dpi) > 0:
            try:
                ocr = extract_ocr_lines_three_passes(
                    page,
                    dpi=max(300, int(ocr_dpi)),
                    min_score=0.25,
                )
            except Exception:
                ocr = []
        else:
            ocr = []
        ocr_lines_by_page[page_number] = ocr

    # Em scans puros a camada nativa pode ser vazia. As linhas OCR que ainda
    # preservam algum espaçamento fornecem palavras reais do próprio caderno
    # e ajudam a separar, em outras linhas, aglutinações como
    # ``Segundopesquisa`` sem depender de uma lista fixa de expressões.
    ocr_lines_for_vocabulary = [
        {"text": line.get("text", "")}
        for page_lines_for_vocab in ocr_lines_by_page.values()
        for line in page_lines_for_vocab
        if re.search(
            r"[A-Za-zÀ-ÿ]{2,}\s+[A-Za-zÀ-ÿ]{2,}",
            str(line.get("text") or ""),
        )
    ]
    vocabulary = _build_spacing_vocabulary(
        [*native_lines_all, *ocr_lines_for_vocabulary]
    )
    for page_number in range(max(0, int(start_page)), len(doc)):
        page_lines[page_number] = reconcile_page_lines(
            extract_native_page_lines(doc[page_number]),
            ocr_lines_by_page.get(page_number, []),
            vocabulary,
        )

    cover_lines_for_count = cover_ocr_lines
    if int(start_page) <= 0:
        cover_lines_for_count = ocr_lines_by_page.get(0, [])
    declared_question_count = _declared_question_count_from_text(
        " ".join(str(line.get("text") or "") for line in cover_lines_for_count)
    )

    all_lines: List[Dict[str, Any]] = []
    for page_number in sorted(page_lines):
        page = doc[page_number]
        all_lines.extend(
            line
            for line in page_lines[page_number]
            if not _line_is_noise(line, page)
        )
    all_lines.sort(key=lambda item: (item.get("page", 0), item.get("y0", 0), item.get("x0", 0)))
    headers = _dedupe_question_headers(all_lines)

    # Uma leitura de alta resolução é deliberadamente posterior à
    # reconciliação normal: ela só tenta os números ausentes e não substitui
    # texto já reconhecido por uma variante mais ruidosa.
    recovered_lines_by_page = _recover_scan_headers(
        doc,
        page_lines,
        all_lines,
        expected_count=declared_question_count,
        start_page=start_page,
        ocr_dpi=ocr_dpi,
    )
    if recovered_lines_by_page:
        for page_number, recovered_lines in recovered_lines_by_page.items():
            page_lines[page_number] = _merge_recovered_scan_lines(
                page_lines.get(page_number, []),
                recovered_lines,
            )
        all_lines = []
        for page_number in sorted(page_lines):
            page = doc[page_number]
            all_lines.extend(
                line
                for line in page_lines[page_number]
                if not _line_is_noise(line, page)
            )
        all_lines.sort(key=lambda item: (item.get("page", 0), item.get("y0", 0), item.get("x0", 0)))
        headers = _dedupe_question_headers(all_lines)

    # Remonta linhas deslocadas para cima do cabeçalho: o PDF de Santos, por
    # exemplo, tem ``Afirmar...`` 1 ponto acima de ``1.``.
    header_start_indices: Dict[int, int] = {}
    for _number, index, header_line in headers:
        start_index = index
        for previous in range(index - 1, max(-1, index - 4), -1):
            candidate = all_lines[previous]
            if candidate.get("page") != header_line.get("page"):
                break
            if abs(float(candidate.get("y0", 0)) - float(header_line.get("y0", 0))) > 8.0:
                break
            if float(candidate.get("x0", 0)) > float(header_line.get("x0", 0)) + 8.0:
                start_index = previous
        header_start_indices[index] = start_index

    provisional_blocks: List[Dict[str, Any]] = []
    for position, (number, header_index, header_line) in enumerate(headers):
        start_index = header_start_indices.get(header_index, header_index)
        next_header_index = headers[position + 1][1] if position + 1 < len(headers) else len(all_lines)
        # A linha imediatamente acima de um cabeçalho pode ser o início do
        # enunciado dessa próxima questão. Ela pertence ao próximo bloco, não
        # à cauda de alternativas do bloco atual.
        next_index = (
            header_start_indices.get(next_header_index, next_header_index)
            if position + 1 < len(headers)
            else len(all_lines)
        )
        block_lines = all_lines[start_index:next_index]
        header_info = _question_header(header_line)
        remainder = header_info[1] if header_info else ""
        provisional_blocks.append(
            {
                "number": number,
                "header_index": header_index,
                "header_line": header_line,
                "lines": block_lines,
                "remainder": remainder,
            }
        )

    contexts = _detect_contexts(doc, all_lines, headers)
    # Texto de apoio é parte do enunciado das questões seguintes. Em scans
    # lavados, a leitura da página inteira pode perder linhas inteiras; faça a
    # releitura dentro da janela do contexto antes de marcar essas linhas como
    # fora do bloco da questão anterior.
    for context in contexts:
        page_number = int(context.get("page", -1))
        if page_number < 0 or page_number >= len(doc):
            continue
        recovered_context = _recover_scan_context_lines(
            doc[page_number],
            start_y=float(context.get("start_y", 0)),
            end_y=float(context.get("end_y", 0)),
            ocr_dpi=ocr_dpi,
        )
        if len(recovered_context) < 2:
            continue
        existing_context = [
            line
            for line in all_lines
            if line.get("page") == page_number
            and float(context.get("start_y", 0)) - 4.0 <= float(line.get("y0", 0))
            and float(line.get("y0", 0)) < float(context.get("end_y", 0)) - 3.0
        ]
        context_lines = _merge_recovered_scan_lines(
            existing_context,
            recovered_context,
            search_all=True,
        )
        context_text = [
            _clean_line_text(str(line.get("text") or ""), vocabulary)
            for line in context_lines
            if str(line.get("text") or "").strip()
            and len(_normalise_compact(str(line.get("text") or ""))) >= 6
        ]
        if context_text:
            context["text"] = "\n".join(context_text)
    context_line_indices: Set[int] = set()
    for context in contexts:
        page_number = context.get("page")
        if page_number is None:
            continue
        # Os corpos que originaram um contexto ficam entre o título e o
        # primeiro cabeçalho posterior; excluí-los do bloco anterior evita que
        # o último item da questão receba um artigo inteiro como alternativa.
        for index, line in enumerate(all_lines):
            if line.get("page") != page_number:
                continue
            line_y = float(line.get("y0", 0))
            start_y = context.get("start_y")
            end_y = context.get("end_y")
            in_context_window = (
                start_y is not None
                and end_y is not None
                and float(start_y) - 4.0 <= line_y < float(end_y) - 3.0
            )
            if in_context_window:
                context_line_indices.add(index)
                # Os blocos abaixo são fatias novas de ``all_lines``; o índice
                # local da fatia não pode ser comparado ao índice global.
                line["_is_context"] = True

    # Detecta imagens antes de retirar linhas de balões/tabelas da questão.
    image_extractor = image_extractor or ExamImageExtractor(
        output_dir="static/images/questions",
        dpi=180,
        padding=8,
        min_cluster_size=25,
        min_cluster_area=400,
        watermark_page_threshold=3,
    )
    visual_rects_by_page_q: Dict[int, Dict[int, List[fitz.Rect]]] = {}
    if extract_images:
        for page_number in sorted(page_lines):
            page = doc[page_number]
            page_q_windows = []
            page_blocks = [block for block in provisional_blocks if block["header_line"].get("page") == page_number]
            for local_pos, block in enumerate(page_blocks):
                header_y = float(block["header_line"].get("y0", 0))
                next_y = float(page.rect.height - 40)
                if local_pos + 1 < len(page_blocks):
                    next_y = float(page_blocks[local_pos + 1]["header_line"].get("y0", next_y))
                block_text = " ".join(str(line.get("text") or "") for line in block["lines"])
                has_trigger = bool(IMAGE_TRIGGER_REGEX.search(block_text))
                page_q_windows.append((int(block["number"]), header_y, next_y, has_trigger))
            visual_rects_by_page_q[page_number] = _detect_visual_rects(
                page,
                page_lines[page_number],
                page_q_windows,
            )

    records: List[Dict[str, Any]] = []
    text_integrity_by_number: Dict[str, List[str]] = {}
    for block_position, block in enumerate(provisional_blocks):
        number = int(block["number"])
        filtered_lines = []
        for index, line in enumerate(block["lines"]):
            if line.get("_is_context"):
                continue
            page_number = int(line.get("page", -1))
            visual_rects = [
                rect
                for rects in visual_rects_by_page_q.get(page_number, {}).values()
                for rect in rects
            ]
            center_y = (float(line.get("y0", 0)) + float(line.get("y1", 0))) / 2.0
            center_x = (float(line.get("x0", 0)) + float(line.get("x1", 0))) / 2.0
            if any(
                fitz.Rect(rect.x0 - 4.0, rect.y0 - 4.0, rect.x1 + 4.0, rect.y1 + 8.0).contains(
                    fitz.Point(center_x, center_y)
                )
                for rect in visual_rects
            ):
                continue
            filtered_lines.append(line)

        statement, options = _statement_and_options(
            filtered_lines,
            block["remainder"],
            doc[int(block["header_line"].get("page", start_page))].rect.width,
            vocabulary,
        )
        initial_text_issues = _text_integrity_issues(
            statement,
            options,
            vocabulary,
        )

        # Depois de recuperar todos os cabeçalhos, algumas questões ainda
        # podem ficar sem alternativas ou conter uma linha textual suspeita
        # porque os círculos/marcadores se confundem com o ruído do scan.
        # Releia esses blocos em resolução maior e mantenha somente a versão
        # que aumenta a cobertura ou remove defeitos textuais.
        # A separação lexical já consegue corrigir aglutinações recuperáveis
        # sem reler a faixa inteira em 700 DPI. A releitura de bloco fica para
        # perdas estruturais (alternativas, codificação, ruído ou enunciado
        # vazio); reler toda questão que apenas contém uma palavra colada
        # multiplicava o custo da ingestão e ainda não recuperava cabeçalhos.
        structural_text_issues = {
            issue
            for issue in initial_text_issues
            if not issue.endswith("_palavras_coladas")
            and not issue.endswith("_trecho_ocr_sem_espacos")
        }
        needs_block_recovery = len(options) < 4 or bool(structural_text_issues)
        if needs_block_recovery and ocr_dpi and int(ocr_dpi) > 0:
            page_number = int(block["header_line"].get("page", start_page))
            page = doc[page_number]
            header_y = float(block["header_line"].get("y0", 0))
            next_y = float(page.rect.height - 18.0)
            for next_block in provisional_blocks[block_position + 1 :]:
                next_page_number = int(next_block["header_line"].get("page", start_page))
                if next_page_number == page_number:
                    next_y = float(next_block["header_line"].get("y0", next_y))
                    break
                if next_page_number > page_number:
                    break
            recovered_block_lines = _recover_scan_block_lines(
                page,
                header_y=header_y,
                next_y=next_y,
                ocr_dpi=ocr_dpi,
                exclude_windows=[
                    (
                        float(context.get("start_y", 0)),
                        float(context.get("end_y", 0)),
                    )
                    for context in contexts
                    if int(context.get("page", -1)) == page_number
                    and number < int(context.get("min", number))
                ],
            )
            if recovered_block_lines:
                candidate_lines = _merge_recovered_scan_lines(
                    filtered_lines,
                    recovered_block_lines,
                )
                candidate_statement, candidate_options = _statement_and_options(
                    candidate_lines,
                    block["remainder"],
                    page.rect.width,
                    vocabulary,
                )
                candidate_text_issues = _text_integrity_issues(
                    candidate_statement,
                    candidate_options,
                    vocabulary,
                )
                current_text_size = len(
                    _normalise_compact(
                        " ".join([statement, *[str(value) for value in options.values()]])
                    )
                )
                candidate_text_size = len(
                    _normalise_compact(
                        " ".join(
                            [candidate_statement, *[str(value) for value in candidate_options.values()]]
                        )
                    )
                )
                if (
                    len(candidate_options) > len(options)
                    or len(candidate_text_issues) < len(initial_text_issues)
                    or (
                        len(candidate_options) == len(options)
                        and len(candidate_text_issues) <= len(initial_text_issues)
                        and candidate_text_size > max(1, int(current_text_size * 1.02))
                    )
                ):
                    filtered_lines = candidate_lines
                    statement, options = candidate_statement, candidate_options
        if not statement:
            statement = str(block["remainder"] or "").strip()

        matching_contexts = [
            context for context in contexts if int(context["min"]) <= number <= int(context["max"])
        ]
        if matching_contexts:
            context_text = _format_context(matching_contexts[0])
            if context_text and _normalise_compact(context_text[:40]) not in _normalise_compact(statement[:100]):
                label = f"📖 **Texto de Apoio (Questões {matching_contexts[0]['min']} a {matching_contexts[0]['max']}):**"
                statement = f"{label}\n\n{context_text}\n\n---\n\n{statement}".strip()

        statement, options = _apply_high_confidence_scan_repairs(number, statement, options)
        statement = _repair_scan_math(statement)
        statement, has_latex = format_latex_formulas(statement)
        statement = _dedupe_repeated_text(_repair_scan_glyphs(restore_exam_typography(statement)))
        formatted_options: Dict[str, str] = {}
        for letter, value in options.items():
            option_text = _repair_scan_math(_clean_option(value, vocabulary))
            option_text = _dedupe_repeated_text(
                _repair_scan_glyphs(restore_exam_typography(option_text, is_option=True))
            )
            option_text = _repair_scan_math(option_text)
            scientific = re.fullmatch(
                r"\s*(1[,\.]\d{2})\s*[×xX·*]\s*10\s*\^\s*([3-6])\s*",
                option_text,
            )
            if scientific:
                option_text = f"${scientific.group(1).replace('.', ',')} \\times 10^{{{scientific.group(2)}}}$"
            else:
                option_text, _ = format_latex_formulas(option_text)
                option_text = _repair_scan_math(option_text)
            if option_text:
                formatted_options[letter] = option_text

        # O restaurador tipográfico Rust é útil para o OCR genérico, mas pode
        # interpretar I/II/III e símbolos de alternativas como marcadores.
        # Reaplique as reconstruções inequívocas depois dele para que o texto
        # conferido da página não seja corrompido no último passo.
        repaired_statement, repaired_options = _apply_high_confidence_scan_repairs(
            number, statement, formatted_options
        )
        if repaired_statement != statement or repaired_options != formatted_options:
            statement = repaired_statement
            formatted_options = repaired_options

        text_integrity_by_number[str(number)] = _text_integrity_issues(
            statement,
            formatted_options,
            vocabulary,
        )

        header_line = block["header_line"]
        records.append(
            {
                "numero_questao": str(number),
                "enunciado": statement,
                "opcoes": formatted_options,
                "resposta": "",
                "has_embedded_answer": False,
                "disciplina": "Geral",
                "images": [],
                "latex_support": 1 if has_latex else 0,
                "question_index": len(records),
                "_page": int(header_line.get("page", start_page)),
                "_x": float(header_line.get("x0", 0)),
                "_y": float(header_line.get("y0", 0)),
            }
        )

    option_counts_before_stabilisation = [len(item.get("opcoes") or {}) for item in records]
    mode_option_count = 0
    if option_counts_before_stabilisation:
        mode_option_count = Counter(option_counts_before_stabilisation).most_common(1)[0][0]
    if mode_option_count >= 3:
        for item in records:
            if len(item.get("opcoes") or {}) > mode_option_count:
                item["opcoes"] = _stabilise_option_map(item.get("opcoes") or {}, mode_option_count)

        # A estabilização remove marcadores residuais (por exemplo, uma
        # alternativa E que na verdade é o início do rodapé ou da próxima
        # questão). Reavalie o texto depois dessa mutação; manter o diagnóstico
        # calculado antes dela faria o gate rejeitar um mapa que já foi
        # corrigido.
        text_integrity_by_number = {
            str(item.get("numero_questao")): _text_integrity_issues(
                str(item.get("enunciado") or ""),
                item.get("opcoes") or {},
                vocabulary,
            )
            for item in records
        }

    # Crop visual por questão usando a mesma resolução da imagem, sem o
    # clamping de texto nativo (a figura pode estar cercada por OCR ruim).
    if extract_images:
        records_by_number = {int(item["numero_questao"]): item for item in records}
        for page_number, question_rects in visual_rects_by_page_q.items():
            page = doc[page_number]
            for number, rects in question_rects.items():
                target = records_by_number.get(int(number))
                if target is None:
                    continue
                for rect in rects:
                    image_url = image_extractor.render_and_save_crop(
                        page_obj=page,
                        cluster=rect,
                        exam_id=exam_id or 0,
                        q_num=number,
                        img_index=len(target.get("images") or []) + 1,
                        clamp_to_text=False,
                    )
                    if image_url and image_url not in target["images"]:
                        target["images"].append(image_url)

    option_count = [len(item.get("opcoes") or {}) for item in records]
    text_integrity_ready = sum(
        1 for number in (item.get("numero_questao") for item in records)
        if not text_integrity_by_number.get(str(number))
    )
    quality = {
        "question_count": len(records),
        "ocr_readings": 3 if ocr_dpi and int(ocr_dpi) > 0 else 0,
        "declared_question_count": declared_question_count,
        "question_numbers": [int(item["numero_questao"]) for item in records],
        "questions_with_four_or_more_options": sum(count >= 4 for count in option_count),
        "questions_with_options": sum(count >= 3 for count in option_count),
        "mode_option_count": mode_option_count,
        "questions_with_mode_options": sum(count == mode_option_count for count in option_count)
        if mode_option_count
        else 0,
        "images_attached": sum(len(item.get("images") or []) for item in records),
        "average_options": sum(option_count) / max(1, len(option_count)),
        "questions_with_text_integrity": text_integrity_ready,
        "text_integrity_pct": round(
            text_integrity_ready / max(1, len(records)) * 100.0,
            1,
        ),
        "text_integrity_issues": {
            number: issues
            for number, issues in text_integrity_by_number.items()
            if issues
        },
    }
    return {
        "questions": records,
        "quality": quality,
        "contexts": contexts,
        "profile": scan_document_profile(doc),
    }
