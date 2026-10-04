# Arquivos para download

Esta pasta reúne os artefatos publicados na branch `codex/concurse-app`. O APK
Android 0.1.5/code6 e o bundle do gateway estão no GitHub. Os nomes mantêm a
versão real gravada no instalador. Verifique o arquivo `SHA256SUMS.txt` antes
de instalar.

A página pública de apresentação e instalação usa os mesmos artefatos deste
inventário. O código e as instruções de publicação ficam em
[`landing/README.md`](../landing/README.md).

## Windows

Os dois instaladores são equivalentes: o MSI é adequado para implantação
administrada e o NSIS é o instalador interativo comum. Eles são x64 e exigem
WebView2. O instalador Windows foi produzido pelo bundle Tauri disponível neste
checkout; a atualização de versão do código-fonte não altera retroativamente o
metadado interno desses binários.

Os instaladores atuais são os da versão `0.1.2`:

- `concurse.io_0.1.2_x64_en-US.msi` e `concurse.io_0.1.2_x64-setup.exe`: release.
- `concurse.io_0.1.2-debug_x64_en-US.msi` e `concurse.io_0.1.2-debug_x64-setup.exe`: debug para diagnóstico.

Os instaladores `0.1.0` anteriores permanecem disponíveis para retrocesso.

Os arquivos de download desta pasta são:

- `concurse-mobile-aarch64-release-v0.1.5-code6-16k.apk`: APK Android atual.
- `concurse-mobile-aarch64-release-v0.1.4-code5-16k.apk`: APK Android anterior.
- `concurse-mobile-aarch64-release-v0.1.3-code4-16k.apk`: APK Android de
  recuperação, sem o motor embarcado.
- `concurse-mobile-aarch64-release-v0.1.2-code3-16k.apk`: APK histórico com o
  erro de inicialização já documentado.
- `concurse.io_0.1.2_x64_en-US.msi` e `concurse.io_0.1.2_x64-setup.exe`:
  instaladores Windows release atuais.
- `concurse.io_0.1.2-debug_x64_en-US.msi` e
  `concurse.io_0.1.2-debug_x64-setup.exe`: instaladores Windows de diagnóstico.
- `concurse.io_0.1.0_x64_en-US.msi` e `concurse.io_0.1.0_x64-setup.exe`:
  instaladores Windows antigos para retrocesso.
- `app-gateway-mobile-hard-switch.ts`: bundle único da função Supabase.
- `SHA256SUMS.txt`: hashes dos artefatos publicados.

## Android

O novo arquivo é
[`concurse-mobile-aarch64-release-v0.1.5-code6-16k.apk`](concurse-mobile-aarch64-release-v0.1.5-code6-16k.apk):
versão `0.1.5`, código Android `6`, ABI `arm64-v8a` e alinhamento de 16 KB.
Foi gerado e assinado localmente com a mesma chave de desenvolvimento do APK
anterior, permitindo instalá-lo como atualização. O arquivo está publicado no
GitHub no commit `73f8cee`; os novos fluxos ainda precisam de confirmação do
deploy da função do Supabase e de teste no aparelho. A tentativa de atualização
por USB não instalou o APK, pois o Redmi estava desconectado. Os dados do
aplicativo foram preservados.

O APK inclui o motor de extração e OCR, usando a mesma lógica de processamento
de provas do desktop. O Supabase mantém a biblioteca, questões e tentativas;
os arquivos são enviados ao Oracle quando a extração termina. A barra inferior
agora contém cinco ícones em uma única linha, com menu hambúrguer no topo.
A auditoria verificou 123 bibliotecas ARM64, incluindo as dos arquivos Python,
com alinhamento para páginas de 16 KB e sem bancos ou chaves privadas no pacote.

O arquivo [`app-gateway-mobile-hard-switch.ts`](app-gateway-mobile-hard-switch.ts)
reúne as alterações da função central para o editor do Supabase e está publicado
no mesmo commit. O deploy e o estado de sucesso no painel do Supabase ainda não
foram verificados por esta sessão.
O [registro da migração](../docs/mobile-migration-audit.md) distingue os testes
concluídos das verificações pendentes.

O carrossel inicial apresenta biblioteca, prática e revisão antes da página de
login. Há navegação por deslize, botões, teclado e pontos de paginação, além de
um atalho para entrar. A verificação do serviço de login evita abrir o navegador
em um endereço indisponível e mantém o erro e a nova tentativa no aplicativo.

A versão nova mantém a correção da configuração inválida `plugins.opener.open`.
O logcat
coletado no Redmi 14C com Android 16/HyperOS em 03/10/2026 confirmou que esse
campo fazia a build 0.1.2/code3 abortar na inicialização; esse encerramento não
foi causado pelo alinhamento de 16 KB ou pelo WebView. O APK
[`0.1.2/code3`](concurse-mobile-aarch64-release-v0.1.2-code3-16k.apk) permanece
disponível e contém o defeito. A versão
[`0.1.3/code4`](concurse-mobile-aarch64-release-v0.1.3-code4-16k.apk), que corrigiu
esse encerramento, também permanece disponível; o usuário confirmou que ela
abriu a tela de login.

O APK anterior [`0.1.4/code5`](concurse-mobile-aarch64-release-v0.1.4-code5-16k.apk)
permanece disponível; essa versão não contém o motor de processamento Android.

A falha de DNS do login em 03/10/2026 foi resolvida após o usuário retomar o
projeto Supabase. O serviço Auth e o redirecionamento para o Google foram
verificados remotamente. O usuário também confirmou que o Google abriu e
retornou ao aplicativo na versão instalada 0.1.3. Os testes visuais no navegador
não foram realizados porque a permissão de acesso foi negada.

O novo APK é destinado a diagnóstico. A distribuição de produção exige
validação no aparelho e uma chave de release própria.

## Arquivos-fonte mais recentes

Os arquivos abaixo são os fontes que implementam o hard switch mobile publicado
junto com os artefatos desta pasta.

### Gateway Supabase

- `supabase/functions/app-gateway/index.ts`
- `supabase/functions/app-gateway/processed-import.ts`
- `supabase/functions/app-gateway/source-url.ts`
- `supabase/functions/app-gateway/study-results.ts`
- `supabase/functions/app-gateway/user-profile.ts`
- `downloads/app-gateway-mobile-hard-switch.ts`: versão única para colar no
  editor do painel.

### Motor Android, OCR e preparação do APK

- `desktop/engine/android/MainActivity.kt`
- `desktop/engine/android/ProcessingService.kt`
- `desktop/engine/android/mobile_engine.py`
- `desktop/engine/android/engine.gradle.kts`
- `desktop/engine/android/engine.pro`
- `desktop/engine/android/network_security_config.xml`
- `desktop/engine/android/requirements.txt`
- `desktop/engine/android/normalize_native_wheels.py`
- `desktop/engine/android/audit_apk.py`
- `desktop/engine/android/EngineSmokeTest.kt`
- `desktop/scripts/prepare-android-engine.mjs`
- `desktop/scripts/collect-android-startup.ps1`

### Interface e serviços compartilhados

- `frontend/src/components/auth/LoginPage.tsx`
- `frontend/src/components/dashboard/DirectIngestModal.tsx`
- `frontend/src/components/dashboard/FoldersView.tsx`
- `frontend/src/components/dashboard/SearchHub.tsx`
- `frontend/src/components/layout/MobileMenu.tsx`
- `frontend/src/components/layout/Navbar.tsx`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/components/layout/navigation.ts`
- `frontend/src/index.css`
- `frontend/src/services/api.ts`
- `frontend/src/services/supabase.ts`
- `frontend/src/types/exam.ts`
- `app_core/async_worker.py`
- `routes/api_v1/exam_api.py`
- `routes/api_v1/exam_media.py`

### Configuração e publicação

- `.gitattributes`: mantém APKs grandes no Git LFS.
- `frontend/.env.mobile`
- `frontend/tsconfig.json`
- `desktop/.cargo/config.toml`
- `desktop/package.json`
- `desktop/src-tauri/tauri.android.conf.json`
- `desktop/src-tauri/tauri.ios.conf.json`
- `desktop/README.md`
- `README.md`

### Testes que acompanham a mudança

- `frontend/src/test/app-routing-preferences.test.tsx`
- `frontend/src/test/auth-login.test.tsx`
- `frontend/src/test/direct-ingest-modal.test.tsx`
- `frontend/src/test/gateway-processed-import.test.ts`
- `frontend/src/test/gateway-study-results.test.ts`
- `frontend/src/test/gateway-user-profile.test.ts`
- `frontend/src/test/mobile-navigation.test.tsx`
- `frontend/src/test/mobile-processing-api.test.ts`
- `frontend/src/test/native-google-login.test.ts`
- `frontend/src/test/search-accessibility.test.tsx`
- `frontend/src/test/setup.ts`

O relatório técnico completo está em `docs/mobile-migration-audit.md`. O arquivo
`.idsig` que pode aparecer ao lado do APK é apenas uma assinatura auxiliar local
e não faz parte do pacote distribuído.
