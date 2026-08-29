//! Suíte abrangente de testes unitários para o motor de tipografia
use super::restore_exam_typography_native;

#[test]
fn test_q12_bullet_markers() {
    let raw = "Karina está organizando uma excursão: - 6 pessoas aceitam qualquer. - 2 pessoas gostam de Amsterdã. - 7 pessoas gostam de Caribe.";
    let res = restore_exam_typography_native(raw, false);
    assert!(res.contains("\n\n- 6 pessoas"));
    assert!(res.contains("\n\n- 2 pessoas"));
    assert!(res.contains("\n\n- 7 pessoas"));
}

#[test]
fn test_q28_english_table_and_options() {
    let raw = "Match column 1 with column 2: Column 1 Word (1) Deck (2) Hull Column 2 (__) The floor (__) The main body";
    let res = restore_exam_typography_native(raw, false);
    assert!(res.contains("Match column 1 with column 2:"));
    assert!(res.contains("**Column 1:**"));
    assert!(res.contains("(1) Deck"));
    assert!(res.contains("(2) Hull"));
    assert!(res.contains("**Column 2:**"));
    assert!(res.contains("(__) The floor"));
}

#[test]
fn test_q33_broken_url_percent_encoding() {
    let raw = "Um sistema operacional.\nhttps://ifg.edu.br/attachments/article/19169/Inform%C3%\nA1tica%20b%C3%A1sica%20para%20o%20estudo%\n20on-line%20(19-12-2020).pdf";
    let res = restore_exam_typography_native(raw, false);
    assert!(res.contains("*(Fonte: https://ifg.edu.br/attachments/article/19169/Informática básica para o estudo on-line (19-12-2020).pdf)*"));
    assert!(!res.contains(".pdf)*\n"));
}

#[test]
fn test_q46_short_numbered_items_and_transitions() {
    let raw = "Apresenta cinco elementos:\n1. Cabeça; 2. Pé\n3. Off\n4. Sonora\n5. Passagem. Esses elementos correspondem a situações em que\n( ) o repórter narra";
    let res = restore_exam_typography_native(raw, false);
    assert!(res.contains("1. Cabeça;"));
    assert!(res.contains("\n\n2. Pé"));
    assert!(res.contains("\n\n3. Off"));
    assert!(res.contains("\n\n4. Sonora"));
    assert!(res.contains("\n\n5. Passagem."));
    assert!(res.contains("\n\nEsses elementos correspondem a situações em que\n\n( ) o repórter narra"));
}

#[test]
fn test_q49_parenthesized_items_and_columns() {
    let raw = "relacionando a coluna 1 com a coluna 2: Coluna 1 (1)Instalação (2)Bem público Coluna 2 (__) Instalação";
    let res = restore_exam_typography_native(raw, false);
    assert!(res.contains("relacionando a coluna 1 com a coluna 2:"));
    assert!(res.contains("**Coluna 1:**"));
    assert!(res.contains("\n\n(1) Instalação"));
    assert!(res.contains("\n\n(2) Bem público"));
    assert!(res.contains("**Coluna 2:**"));
}

#[test]
fn test_q7_paired_sentences_slash_continuation() {
    let raw = "(__) ACENDER a luz.\n/ ASCENDER socialmente\n(__) Ele vai COLHER as flores.\n/ A COLHER está sobre a mesa.";
    let res = restore_exam_typography_native(raw, false);
    assert!(res.contains("(__) ACENDER a luz. / ASCENDER socialmente"));
    assert!(res.contains("(__) Ele vai COLHER as flores. / A COLHER está sobre a mesa."));
}

#[test]
fn test_poem_stanza_preservation() {
    let raw = "Considere o poema de Fernando Pessoa:\n\nO poeta é um fingidor.\nFinge tão completamente\nQue chega a fingir que é dor\nA dor que deveras sente.\n\nAssinale a alternativa correta.";
    let res = restore_exam_typography_native(raw, false);
    assert!(res.contains("> O poeta é um fingidor."));
    assert!(res.contains("> Finge tão completamente"));
    assert!(res.contains("> Que chega a fingir que é dor"));
    assert!(res.contains("> A dor que deveras sente."));
    assert!(res.contains("Assinale a alternativa correta."));
}

#[test]
fn test_idempotence() {
    let raw = "1. Cabeça; 2. Pé\n\n*(Fonte: https://ifg.edu.br/teste.pdf)*\n\n(__) ACENDER a luz. / ASCENDER socialmente";
    let first_pass = restore_exam_typography_native(raw, false);
    let second_pass = restore_exam_typography_native(&first_pass, false);
    assert_eq!(first_pass, second_pass, "O motor de tipografia deve ser estritamente idempotente");
}
