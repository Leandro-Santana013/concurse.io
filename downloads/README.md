# Arquivos para download

Esta pasta contém os artefatos distribuídos com a branch `codex/concurse-app`.
Os nomes mantêm a versão real gravada no instalador. Verifique o arquivo
`SHA256SUMS.txt` antes de instalar.

## Windows

Os dois instaladores são equivalentes: o MSI é adequado para implantação
administrada e o NSIS é o instalador interativo comum. Eles são x64 e exigem
WebView2. O instalador Windows foi produzido pelo bundle Tauri disponível neste
checkout; a atualização de versão do código-fonte não altera retroativamente o
metadado interno desses binários.

## Android

O APK é `arm64-v8a`, assinado com uma chave de desenvolvimento e destinado a
diagnóstico. Ele permanece disponível porque reproduz o abort nativo relatado
em alguns aparelhos Redmi com Android 16/HyperOS. Não use esse APK como
distribuição pública até a correção do WebView e a assinatura com uma chave de
release própria.
