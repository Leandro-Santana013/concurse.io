package io.concurse.desktop;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Build;
import android.view.View;
import android.view.WindowInsets;
import android.graphics.Insets;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import com.chaquo.python.Python;
import com.chaquo.python.PyObject;
import java.net.HttpURLConnection;
import java.net.URL;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Tests the release APK without references to Kotlin or AndroidX APIs pruned by R8. */
@RunWith(AndroidJUnit4.class)
public class EngineSmokeTest {
    private Activity startEngine() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Activity activity = instrumentation.startActivitySync(new Intent(instrumentation.getTargetContext(), MainActivity.class)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        long deadline = System.currentTimeMillis() + 90000;
        int status = 0;
        while (System.currentTimeMillis() < deadline) {
            try {
                HttpURLConnection connection = (HttpURLConnection)new URL("http://127.0.0.1:45873/health").openConnection();
                connection.setConnectTimeout(1000);
                connection.setReadTimeout(1000);
                status = connection.getResponseCode();
                connection.disconnect();
                if (status == 200) break;
            } catch (Exception ignored) { }
            Thread.sleep(250);
        }
        assertEquals("O motor Python deve iniciar com as bibliotecas do APK", 200, status);
        return activity;
    }

    @Test public void embeddedProcessingStartsAndReadsNativeAndScannedPdf() throws Exception {
        Activity activity = startEngine();
        InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> {
            View content = activity.findViewById(android.R.id.content);
            if (Build.VERSION.SDK_INT >= 30) {
                WindowInsets windowInsets = content.getRootWindowInsets();
                assertNotNull(windowInsets);
                Insets expected = windowInsets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                assertEquals(expected.top, content.getPaddingTop());
                assertEquals(expected.bottom, content.getPaddingBottom());
                assertEquals(expected.left, content.getPaddingLeft());
                assertEquals(expected.right, content.getPaddingRight());
            }
        });
        // Tauri owns one Activity/event loop per process. Keep all checks in
        // one test so the runner does not tear it down between checks.
        execute(NETWORK_PROGRAM);
        execute(PDF_PROGRAM);
        if ("true".equals(InstrumentationRegistry.getArguments().getString("liveSearch", "false"))) {
            execute(LIVE_SEARCH_PROGRAM);
        }
    }

    private static void execute(String program) {
        PyObject builtins = Python.getInstance().getModule("builtins");
        // A Java caller has no Python frame to provide exec's default globals.
        builtins.callAttr("exec", program, builtins.callAttr("dict"));
    }

    private static String code(String... lines) {
        StringBuilder result = new StringBuilder();
        for (String line : lines) result.append(line).append('\n');
        return result.toString();
    }
    private static final String PDF_PROGRAM = code(
        "import json, os, tempfile",
        "from pathlib import Path",
        "import fitz, numpy as np, cv2",
        "from cryptography.hazmat.primitives.ciphers.aead import AESGCM",
        "from services.auth import create_session_token, read_session_token",
        "from services.crawlers import get_ddgs_class",
        "from rapidocr_onnxruntime import RapidOCR",
        "assert os.environ.get('CRYPTOGRAPHY_OPENSSL_NO_LEGACY') == '1'",
        "aes = AESGCM(AESGCM.generate_key(bit_length=256))",
        "nonce = os.urandom(12)",
        "protected = aes.encrypt(nonce, b'android engine', b'concurse')",
        "assert aes.decrypt(nonce, protected, b'concurse') == b'android engine'",
        "assert read_session_token(create_session_token(42)) == 42",
        "ddgs = get_ddgs_class()",
        "assert ddgs is not None, 'O backend de busca deve estar incluido no APK'",
        "with ddgs(timeout=10):",
        "    pass",
        "cv2.setNumThreads(2)",
        "with tempfile.TemporaryDirectory() as work:",
        "    pdf = fitz.open()",
        "    page = pdf.new_page(width=720, height=480)",
        "    page.insert_text((45, 80), 'QUESTAO 01 - ESTUDO PARA CONCURSO', fontsize=24)",
        "    page.insert_text((45, 130), 'A) Primeira alternativa. B) Segunda alternativa.', fontsize=20)",
        "    path = Path(work) / 'native.pdf'",
        "    pdf.save(path)",
        "    with fitz.open(path) as saved:",
        "        assert 'CONCURSO' in saved[0].get_text()",
        "        pixmap = saved[0].get_pixmap(dpi=120, alpha=False)",
        "        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)",
        "        engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)",
        "        lines, _ = engine(image)",
        "        text = ' '.join(item[1] for item in (lines or []))",
        "        assert 'CONCURSO' in text.upper(), text",
        "    pdf.close()",
        "print('CONCURSE_ANDROID_ENGINE_OK: API, AES-GCM, session, search backend, PDF text and OCR passed', flush=True)"
    );
    private static final String NETWORK_PROGRAM = code(
        "import os, socket",
        "from urllib.parse import urlsplit",
        "import requests",
        "from concurrent.futures import ThreadPoolExecutor",
        "from services.auth.supabase_auth import verify_supabase_access_token, SupabaseAuthError",
        "url = os.environ['SUPABASE_URL']",
        "host = urlsplit(url).hostname",
        "try:",
        "    probe = requests.post('http://127.0.0.1:45873/api/v1/auth/supabase/exchange', json={",
        "        'access_token': 'concurse-network-probe-no-session'",
        "    }, timeout=18)",
        "    print('CONCURSE_NETWORK_ROUTE_STATUS: %s' % probe.status_code, flush=True)",
        "    assert probe.status_code == 401, 'Invalid probe must reach Auth and be rejected, not fail with network outage: %s' % probe.status_code",
        "    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)",
        "    print('CONCURSE_NETWORK_DNS_OK: %s, %s addresses' % (host, len(addresses)), flush=True)",
        "    response = requests.get(url + '/auth/v1/health', headers={",
        "        'apikey': os.environ['SUPABASE_PUBLISHABLE_KEY']",
        "    }, timeout=12)",
        "    print('CONCURSE_NETWORK_HTTP_STATUS: %s' % response.status_code, flush=True)",
        "    assert response.status_code == 200, 'Supabase health status: %s' % response.status_code",
        "    def check_worker():",
        "        try:",
        "            verify_supabase_access_token('concurse-network-probe-no-session')",
        "        except SupabaseAuthError as rejected:",
        "            cause = rejected.__cause__",
        "            if isinstance(cause, requests.HTTPError) and cause.response.status_code in (401, 403):",
        "                print('CONCURSE_NETWORK_WORKER_OK: invalid probe rejected by Supabase', flush=True)",
        "                return",
        "            print('CONCURSE_NETWORK_WORKER_FAILED: %s: %s' % (type(cause).__name__, str(cause)[:600]), flush=True)",
        "            raise",
        "        raise AssertionError('An invalid probe must not authenticate')",
        "    with ThreadPoolExecutor(max_workers=1) as pool:",
        "        pool.submit(check_worker).result(timeout=20)",
        "except Exception as error:",
        "    # Only the public health URL is requested; no user session is accessed.",
        "    print('CONCURSE_NETWORK_FAILED: %s: %s' % (type(error).__name__, str(error)[:600]), flush=True)",
        "    raise"
    );
    // Optional public-source validation. It never authenticates as the user,
    // writes a central record, or reports the temporary extraction as a library import.
    private static final String LIVE_SEARCH_PROGRAM = code(
        "import hashlib, requests, time",
        "from services.crawlers.scraper_service import _scrape_idcap_pdfs",
        "from services.search import interpret_search_query_deterministic",
        "from services.pdf_pipeline.hybrid_extractor import parse_exam_document",
        "query = 'Fiscal de Postura idecap'",
        "started = time.monotonic()",
        "cards = _scrape_idcap_pdfs(query, interpret_search_query_deterministic(query))",
        "print('CONCURSE_LIVE_SEARCH_RESULTS: %s, %.2fs' % (len(cards), time.monotonic() - started), flush=True)",
        "matches = [item for item in cards if 'ibirataia' in item['title'].lower()]",
        "assert matches, 'A busca real deve localizar o caderno de Ibirataia IDCAP'",
        "response = requests.get(matches[0]['url'], timeout=20)",
        "response.raise_for_status()",
        "assert response.content.startswith(b'%PDF-'), 'O resultado deve baixar um PDF real'",
        "assert hashlib.sha256(response.content).hexdigest() == '34891104503e03d489554f35a3e36acf9405e4f8744b7952ddccea438e30b7e0'",
        "questions = parse_exam_document(response.content, extract_images=False)",
        "assert len(questions) == 50, len(questions)",
        "assert all(len(item['opcoes']) == 4 for item in questions)",
        "assert all(item.get('resposta') in ('A', 'B', 'C', 'D') for item in questions)",
        "assert questions[0]['resposta'] == 'D'",
        "assert questions[48]['resposta'] == 'B'",
        "print('CONCURSE_LIVE_IDCAP_OK: public search, PDF download, 50 questions, 50 answers, Q1 D and Q49 B passed', flush=True)"
    );
}
