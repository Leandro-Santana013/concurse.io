// concurse.io - pacote de publicacao do hard switch mobile. Gerado dos cinco arquivos de app-gateway.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
//#region ../supabase/functions/app-gateway/user-profile.ts
const visibleText = (value) => {
	const text = String(value || "").trim();
	return /^(enc|hmac):v1:/.test(text) ? "" : text;
};
const presentInternalUser = (stored, identity) => {
	const metadata = identity.user_metadata || {};
	const legacyEmail = visibleText(stored.email);
	return {
		id: Number(stored.id),
		supabase_auth_id: String(stored.supabase_auth_id || identity.id),
		email: visibleText(identity.email) || (/@users\.invalid$/i.test(legacyEmail) ? "" : legacyEmail),
		name: visibleText(metadata.full_name) || visibleText(metadata.name) || visibleText(stored.name) || "Concurseiro",
		picture: visibleText(metadata.avatar_url) || visibleText(metadata.picture) || visibleText(stored.picture)
	};
};
const presentRankingUser = (stored, currentUser, identity) => {
	const metadata = identity?.user_metadata || {};
	const isCurrentUser = Number(stored.id) === Number(currentUser.id);
	return {
		id: Number(stored.id),
		name: (isCurrentUser ? currentUser.name : "") || visibleText(metadata.full_name) || visibleText(metadata.name) || visibleText(stored.name) || "Concurseiro",
		picture: (isCurrentUser ? currentUser.picture : "") || visibleText(metadata.avatar_url) || visibleText(metadata.picture) || visibleText(stored.picture)
	};
};
//#endregion
//#region ../supabase/functions/app-gateway/source-url.ts
const trackingKeys = /* @__PURE__ */ new Set([
	"fbclid",
	"gclid",
	"mc_cid",
	"mc_eid",
	"ref",
	"referrer"
]);
function normalizeSourceUrl(value) {
	const url = new URL(value.trim());
	if (!["http:", "https:"].includes(url.protocol)) throw new Error("A fonte deve ser um endereço HTTP ou HTTPS.");
	url.hash = "";
	url.hostname = url.hostname.toLowerCase().replace(/\.$/, "");
	url.pathname = url.pathname.replace(/\/{2,}/g, "/").replace(/\/$/, "") || "/";
	const entries = [...url.searchParams.entries()].filter(([key]) => !key.toLowerCase().startsWith("utm_") && !trackingKeys.has(key.toLowerCase())).sort(([leftKey, leftValue], [rightKey, rightValue]) => leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0);
	url.search = new URLSearchParams(entries).toString();
	return url.toString();
}
async function sourceKey(value) {
	const bytes = new TextEncoder().encode(normalizeSourceUrl(value));
	return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
async function ownedSourceKey(userId, value) {
	const bytes = new TextEncoder().encode(`user:${userId}|source:${normalizeSourceUrl(value)}`);
	return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
function isPublicSourceUrl(value) {
	if (typeof value !== "string") return false;
	try {
		const url = new URL(value);
		if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return false;
		const host = url.hostname.toLowerCase().replace(/\.$/, "");
		if (!host.includes(".") || host.endsWith(".localhost") || host.endsWith(".local")) return false;
		if (/^(?:0\.|10\.|127\.|169\.254\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(host)) return false;
		if (host.includes(":")) return false;
		return true;
	} catch {
		return false;
	}
}
//#endregion
//#region ../supabase/functions/app-gateway/processed-import.ts
var ImportError = class extends Error {
	status;
	constructor(message, status = 400) {
		super(message);
		this.status = status;
	}
};
const mediaObject = (value) => {
	if (!value) return null;
	if (typeof value !== "string" || !/^exams\/[a-zA-Z0-9/_\-.]+$/.test(value) || value.split("/").includes("..")) throw new ImportError("O caminho do arquivo da prova é inválido.");
	return `oci://${value}`;
};
function decodeProcessedImport(payload) {
	let document;
	try {
		const binary = atob(payload.data_base64 || "");
		document = JSON.parse(new TextDecoder().decode(Uint8Array.from(binary, (char) => char.charCodeAt(0))));
	} catch {
		throw new ImportError("Envie o JSON das questões extraídas no dispositivo.");
	}
	if (!document || !Array.isArray(document.questions) || document.questions.length < 5) throw new ImportError("A extração deve conter pelo menos cinco questões válidas.");
	const questions = document.questions;
	if (questions.some((question) => !question || typeof question.statement !== "string" || !question.statement.trim() || !question.options || typeof question.options !== "object" || Array.isArray(question.options) || Object.keys(question.options).length < 2 || !/^(?:[A-E]|X)?$/i.test(String(question.correct_answer || "").trim()))) throw new ImportError("A extração contém questões ou alternativas incompletas.");
	return {
		questions,
		title: String(payload.title || document.title || payload.filename || "Prova importada").slice(0, 300),
		source_url: mediaObject(payload.source_object),
		gabarito_url: mediaObject(payload.gabarito_object) || (isPublicSourceUrl(payload.gabarito_url) ? payload.gabarito_url : null)
	};
}
async function importIdentity(userId, payload) {
	const value = String(payload.source_object || payload.import_key || "");
	if (!value) return null;
	const bytes = new TextEncoder().encode(`user:${userId}|${value}`);
	const source_key = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map((byte) => byte.toString(16).padStart(2, "0")).join("");
	return {
		source_key,
		source_url: `upload://user-${userId}/${source_key}`
	};
}
async function importProcessedExam(db, userId, payload, resolveImage) {
	const document = decodeProcessedImport(payload);
	const identity = await importIdentity(userId, payload);
	const aliases = [];
	if (isPublicSourceUrl(payload.source_url)) {
		const normalized = normalizeSourceUrl(payload.source_url);
		const { data: catalog, error: catalogError } = await db.from("exam_catalog").select("id").in("source_url", [payload.source_url, normalized]).limit(1);
		if (catalogError) throw new Error(catalogError.message);
		if (catalog?.length) aliases.push({
			source_key: await sourceKey(payload.source_url),
			source_url: normalized.slice(0, 500),
			shared: true
		});
		const key = await ownedSourceKey(userId, payload.source_url);
		aliases.push({
			source_key: key,
			source_url: `upload://user-${userId}/${key}`,
			shared: false
		});
	}
	if (identity) aliases.push({
		...identity,
		shared: false
	});
	const link = async (examId) => {
		const { error } = await db.from("user_exams").upsert({
			user_id: userId,
			exam_id: examId,
			created_at: (/* @__PURE__ */ new Date()).toISOString()
		}, { onConflict: "user_id,exam_id" });
		if (error) throw new Error(error.message);
	};
	const existingImport = async () => {
		for (const source of aliases) {
			const { data: alias, error } = await db.from("exam_sources").select("exam_id,created_at").eq("source_key", source.source_key).maybeSingle();
			if (error) throw new Error(error.message);
			if (!alias) continue;
			const { data: exam, error: examError } = await db.from("exams").select("id,title,status,user_id,doc_type").eq("id", alias.exam_id).single();
			if (examError) throw new Error(examError.message);
			if (!source.shared && Number(exam.user_id) !== userId) throw new ImportError("Importação não atribuída à sua conta.", 403);
			if (exam.doc_type === "generated_session") throw new ImportError("Um simulado não pode substituir a prova original.");
			if (exam.status !== "Aprovada") {
				const started = new Date(alias.created_at).valueOf();
				if (exam.status === "Erro" || Number.isFinite(started) && Date.now() - started > 6e5) {
					await db.from("exams").update({
						status: "Erro",
						progress: -1,
						error_type: "sync_interrupted",
						progress_message: "Envio interrompido; uma nova tentativa foi iniciada"
					}).eq("id", exam.id);
					const { error: releaseError } = await db.from("exam_sources").delete().eq("source_key", source.source_key).eq("exam_id", exam.id);
					if (releaseError) throw new Error(releaseError.message);
					continue;
				}
				throw new ImportError("O envio anterior ainda não terminou. Tente novamente em instantes.", 409);
			}
			const { count, error: countError } = await db.from("questions").select("id", {
				count: "exact",
				head: true
			}).eq("exam_id", exam.id);
			if (countError) throw new Error(countError.message);
			if (!count || count < 5) {
				const { error: releaseError } = await db.from("exam_sources").delete().eq("source_key", source.source_key).eq("exam_id", exam.id);
				if (releaseError) throw new Error(releaseError.message);
				continue;
			}
			await link(Number(exam.id));
			return {
				exam_id: Number(exam.id),
				title: String(exam.title),
				status: "Aprovada",
				progress: 100,
				reused: true,
				already_in_library: true,
				message: "Prova já sincronizada na biblioteca."
			};
		}
		return null;
	};
	const existing = await existingImport();
	if (existing) return existing;
	const hasAnswers = document.questions.filter((question) => String(question.correct_answer || "").trim()).length;
	const { data: created, error } = await db.from("exams").insert({
		title: document.title,
		status: "Processando",
		user_id: userId,
		source_url: document.source_url,
		gabarito_url: document.gabarito_url,
		has_official_answers: hasAnswers === document.questions.length ? 1 : 0,
		answer_key_source: hasAnswers ? "imported" : "none",
		doc_type: "caderno_questoes",
		gabarito_coverage: 100 * hasAnswers / document.questions.length,
		progress: 95,
		progress_message: "Recebendo questões e arquivos do dispositivo"
	}).select("id").single();
	if (error || !created) throw new Error(error?.message || "Não foi possível criar a prova.");
	const examId = Number(created.id);
	for (const { shared: _shared, ...alias } of aliases) {
		const { error: identityError } = await db.from("exam_sources").insert({
			...alias,
			exam_id: examId,
			created_at: (/* @__PURE__ */ new Date()).toISOString()
		});
		if (identityError) {
			await db.from("exam_sources").delete().eq("exam_id", examId);
			await db.from("exams").delete().eq("id", examId).eq("user_id", userId);
			const raced = await existingImport();
			if (raced) return raced;
			throw new Error(identityError.message);
		}
	}
	try {
		const rows = [];
		for (const [index, question] of document.questions.entries()) {
			const optionImages = {};
			for (const [key, values] of Object.entries(question.option_images || {})) optionImages[key] = await Promise.all((Array.isArray(values) ? values : []).map((value, slot) => resolveImage(value, examId, index + 1, `o${key}${slot}`)));
			rows.push({
				exam_id: examId,
				statement: question.statement,
				options: JSON.stringify(question.options),
				correct_answer: String(question.correct_answer || "").trim().toUpperCase(),
				subject: String(question.subject || "Geral").slice(0, 100),
				images: JSON.stringify(await Promise.all((Array.isArray(question.images) ? question.images : []).map((value) => resolveImage(value, examId, index + 1, "q")))),
				option_images: JSON.stringify(optionImages),
				numero_questao: String(question.numero_questao || index + 1),
				question_index: index,
				latex_support: question.latex_support ? 1 : 0
			});
		}
		const { error: questionsError } = await db.from("questions").insert(rows);
		if (questionsError) throw new Error(questionsError.message);
		await link(examId);
		const { error: readyError } = await db.from("exams").update({
			status: "Aprovada",
			progress: 100,
			progress_message: "Prova pronta",
			error_type: null
		}).eq("id", examId);
		if (readyError) throw new Error(readyError.message);
	} catch (failure) {
		await db.from("exams").update({
			status: "Erro",
			progress: -1,
			progress_message: "O envio da extração falhou",
			error_type: "sync_failed"
		}).eq("id", examId);
		await db.from("exam_sources").delete().eq("exam_id", examId);
		throw failure;
	}
	return {
		exam_id: examId,
		title: document.title,
		status: "Aprovada",
		progress: 100,
		reused: false,
		already_in_library: true,
		message: "Prova e arquivos sincronizados na biblioteca."
	};
}
//#endregion
//#region ../supabase/functions/app-gateway/study-results.ts
function gradeAttempt(questions, answers) {
	let score = 0;
	const detailed_answers = {};
	const feedback_per_subject = {};
	questions.forEach((question, index) => {
		const key = question.numero_questao || String(index + 1);
		const user_answer = String(answers[String(question.id)] || answers[key] || answers[String(index + 1)] || "").trim().toUpperCase();
		const correct_answer = String(question.correct_answer || "").trim().toUpperCase();
		const is_correct = Boolean(correct_answer && (correct_answer === "X" || user_answer === correct_answer));
		const subject = question.subject || "Geral";
		if (is_correct) score += 1;
		detailed_answers[key] = {
			question_id: question.id,
			user_answer,
			correct_answer,
			is_correct,
			subject
		};
		const feedback = feedback_per_subject[subject] ||= {
			total: 0,
			correct: 0,
			percentage: 0
		};
		feedback.total += 1;
		if (is_correct) feedback.correct += 1;
	});
	Object.values(feedback_per_subject).forEach((feedback) => {
		feedback.percentage = Number((100 * feedback.correct / feedback.total).toFixed(1));
	});
	return {
		score,
		total: questions.length,
		percentage: questions.length ? Number((100 * score / questions.length).toFixed(1)) : 0,
		detailed_answers,
		feedback_per_subject
	};
}
const dayKey = (date) => new Intl.DateTimeFormat("en-CA", {
	timeZone: "America/Sao_Paulo",
	year: "numeric",
	month: "2-digit",
	day: "2-digit"
}).format(date);
function studyOverview(attempts, now = /* @__PURE__ */ new Date()) {
	const total_questions = attempts.reduce((sum, item) => sum + Number(item.total || 0), 0);
	const total_correct = attempts.reduce((sum, item) => sum + Number(item.score || 0), 0);
	const seconds = attempts.reduce((sum, item) => sum + Math.max(0, Number(item.elapsed_seconds || 0)), 0);
	const hours = Math.floor(seconds / 3600);
	const minutes = Math.floor(seconds % 3600 / 60);
	const days = new Set(attempts.map((item) => {
		const text = String(item.created_at || "");
		if (/Z$|[+-]\d\d:\d\d$/.test(text)) {
			const parsed = new Date(text);
			return Number.isFinite(parsed.valueOf()) ? dayKey(parsed) : "";
		}
		return /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(0, 10) : "";
	}));
	const cursor = /* @__PURE__ */ new Date(`${dayKey(now)}T12:00:00Z`);
	if (!days.has(dayKey(cursor))) cursor.setUTCDate(cursor.getUTCDate() - 1);
	let streak = 0;
	while (days.has(dayKey(cursor))) {
		streak += 1;
		cursor.setUTCDate(cursor.getUTCDate() - 1);
	}
	return {
		total_exams: new Set(attempts.map((item) => Number(item.exam_id))).size,
		total_questions,
		total_correct,
		global_accuracy: total_questions ? Number((100 * total_correct / total_questions).toFixed(1)) : 0,
		streak,
		study_time: hours ? `${hours}h ${minutes}m` : `${minutes}m`
	};
}
//#endregion
//#region ../supabase/functions/app-gateway/index.ts
const corsHeaders = {
	"Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, range",
	"Access-Control-Allow-Methods": "GET, HEAD, OPTIONS, POST, PUT, DELETE",
	"Access-Control-Allow-Origin": Deno.env.get("APP_CORS_ORIGIN") || "*",
	"Vary": "Origin"
};
const json = (body, status = 200) => new Response(JSON.stringify(body), {
	status,
	headers: {
		...corsHeaders,
		"Content-Type": "application/json; charset=utf-8"
	}
});
const nowIso = () => (/* @__PURE__ */ new Date()).toISOString();
const readAll = async (query) => {
	const rows = [];
	for (let offset = 0;; offset += 1e3) {
		const { data, error } = await query().range(offset, offset + 999);
		if (error) throw new Error(error.message);
		rows.push(...data || []);
		if (!data || data.length < 1e3) return rows;
	}
};
const parseJson = (value, fallback) => {
	if (value === null || value === void 0 || value === "") return fallback;
	try {
		return typeof value === "string" ? JSON.parse(value) : value;
	} catch {
		return fallback;
	}
};
const supabaseUrl = Deno.env.get("SUPABASE_URL") || "";
const anonKey = Deno.env.get("SUPABASE_ANON_KEY") || Deno.env.get("SUPABASE_PUBLISHABLE_KEY") || "";
const serviceKey = (() => {
	const raw = Deno.env.get("SUPABASE_SECRET_KEYS") || "";
	try {
		const parsed = JSON.parse(raw);
		const named = String(parsed.default || Object.values(parsed)[0] || "").trim();
		if (named) return named;
	} catch {}
	return Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
})();
const accessToken = (request) => {
	const value = request.headers.get("Authorization") || "";
	return value.toLowerCase().startsWith("bearer ") ? value.slice(7).trim() : "";
};
const clientsFor = (token) => {
	if (!supabaseUrl || !anonKey || !serviceKey) throw new Error("Supabase não está configurado na função.");
	return {
		auth: createClient(supabaseUrl, anonKey, {
			auth: {
				persistSession: false,
				autoRefreshToken: false
			},
			global: { headers: { Authorization: `Bearer ${token}` } }
		}),
		db: createClient(supabaseUrl, serviceKey, { auth: {
			persistSession: false,
			autoRefreshToken: false
		} })
	};
};
const authenticate = async (request) => {
	const token = accessToken(request);
	if (!token) throw new Response(JSON.stringify({ error: "É necessário estar autenticado." }), {
		status: 401,
		headers: {
			...corsHeaders,
			"Content-Type": "application/json; charset=utf-8"
		}
	});
	const { auth, db } = clientsFor(token);
	const { data, error } = await auth.auth.getUser(token);
	if (error || !data.user) throw new Response(JSON.stringify({ error: "Sessão Supabase inválida ou expirada." }), {
		status: 401,
		headers: {
			...corsHeaders,
			"Content-Type": "application/json; charset=utf-8"
		}
	});
	return {
		authUser: data.user,
		db
	};
};
const ensureInternalUser = async (db, authUser) => {
	const metadata = authUser.user_metadata || {};
	const { data: existing, error: lookupError } = await db.from("users").select("id,email,name,picture,supabase_auth_id").eq("supabase_auth_id", authUser.id).maybeSingle();
	if (lookupError) throw new Error(`Não foi possível localizar a conta: ${lookupError.message}`);
	if (existing) return presentInternalUser(existing, authUser);
	const row = {
		google_id: `supabase:${authUser.id}`,
		supabase_auth_id: authUser.id,
		email: authUser.email || `supabase-${authUser.id}@users.invalid`,
		name: String(metadata.full_name || metadata.name || "Concurseiro"),
		picture: String(metadata.avatar_url || metadata.picture || "")
	};
	const { data: created, error: createError } = await db.from("users").insert(row).select("id,email,name,picture,supabase_auth_id").single();
	if (createError) {
		const { data: raced } = await db.from("users").select("id,email,name,picture,supabase_auth_id").eq("supabase_auth_id", authUser.id).maybeSingle();
		if (raced) return presentInternalUser(raced, authUser);
		throw new Error(`Não foi possível criar a conta: ${createError.message}`);
	}
	return presentInternalUser(created, authUser);
};
const mediaUrlForPrefix = (value, prefix) => {
	const raw = String(value || "").trim();
	if (!raw || /^data:/i.test(raw) || /^https?:\/\//i.test(raw)) return raw;
	const normalized = raw.replaceAll("\\", "/");
	const marker = normalized.indexOf(`${prefix}/`);
	const filename = marker >= 0 ? normalized.slice(marker + prefix.length + 1) : normalized.split("/").pop() || "";
	if (!filename) return raw;
	const par = prefix === "questions" ? Deno.env.get("OCI_MEDIA_READ_QUESTIONS_PAR_URL") || Deno.env.get("OCI_MEDIA_READ_PAR_URL") || "" : Deno.env.get("OCI_MEDIA_READ_EXAMS_PAR_URL") || Deno.env.get("OCI_MEDIA_READ_PAR_URL") || "";
	if (!par) return raw;
	return `${par.replace(/\/+$/, "")}/${prefix}/${filename.split("/").map(encodeURIComponent).join("/")}`;
};
const mediaUrl = (value) => mediaUrlForPrefix(value, "questions");
const examMediaUrl = (value) => mediaUrlForPrefix(value, "exams");
const storedUrl = (value) => {
	const raw = String(value || "").trim();
	if (!raw.startsWith("oci://")) return value || null;
	return examMediaUrl(raw.slice(6));
};
const writeParFor = (objectPath) => {
	const prefix = objectPath.split("/", 1)[0];
	return (prefix === "questions" ? Deno.env.get("OCI_MEDIA_WRITE_QUESTIONS_PAR_URL") : prefix === "exams" ? Deno.env.get("OCI_MEDIA_WRITE_EXAMS_PAR_URL") : void 0) || Deno.env.get("OCI_MEDIA_WRITE_PAR_URL") || "";
};
const uploadObject = async (objectPath, bytes, contentType) => {
	const base = writeParFor(objectPath);
	if (!base) throw new Error("O upload não está configurado: faltam as PARs de escrita do Oracle.");
	const target = `${base.replace(/\/+$/, "")}/${objectPath.split("/").map(encodeURIComponent).join("/")}`;
	const response = await fetch(target, {
		method: "PUT",
		headers: {
			"content-type": contentType,
			"content-length": String(bytes.byteLength)
		},
		body: bytes
	});
	if (!response.ok) throw new Error(`O Oracle recusou o upload (${response.status}).`);
};
const dataUrlBytes = (value) => {
	const match = String(value || "").match(/^data:([^;,]+)?;base64,(.*)$/s);
	if (!match) return null;
	const binary = atob(match[2]);
	return {
		contentType: match[1] || "application/octet-stream",
		bytes: Uint8Array.from(binary, (character) => character.charCodeAt(0))
	};
};
const importedMedia = async (value, examId, questionIndex, slot) => {
	const decoded = dataUrlBytes(value);
	if (!decoded) return value;
	const extension = decoded.contentType.split("/")[1]?.replace(/[^a-z0-9]+/gi, "") || "bin";
	const objectPath = `questions/import-${examId}-${questionIndex}-${slot}-${crypto.randomUUID()}.${extension}`;
	await uploadObject(objectPath, decoded.bytes, decoded.contentType);
	return objectPath;
};
const questionPayload = (row) => ({
	id: Number(row.id),
	numero_questao: String(row.numero_questao || row.question_index || ""),
	statement: String(row.statement || ""),
	options: parseJson(row.options, {}),
	correct_answer: String(row.correct_answer || ""),
	is_annulled: /^\s*\(?\s*quest(?:ão|ao)\s+anulada\b/i.test(String(row.statement || "")),
	subject: String(row.subject || "Geral"),
	images: parseJson(row.images, []).map(mediaUrl),
	option_images: Object.fromEntries(Object.entries(parseJson(row.option_images, {})).map(([key, images]) => [key, (Array.isArray(images) ? images : []).map(mediaUrl)])),
	has_official_answer: Boolean(String(row.correct_answer || "").trim()),
	latex_support: Boolean(row.latex_support),
	context_text: null
});
const loadExamQuestions = async (db, examId) => {
	const [{ data: session, error: sessionError }, { data: regularQuestions, error: questionsError }] = await Promise.all([db.from("generated_exam_sessions").select("question_ids_json").eq("exam_id", examId).maybeSingle(), db.from("questions").select("*").eq("exam_id", examId).order("question_index", {
		ascending: true,
		nullsFirst: false
	}).order("id", { ascending: true })]);
	if (sessionError || questionsError) throw new Error(sessionError?.message || questionsError?.message || "Falha ao carregar questoes.");
	const questionIds = session ? parseJson(session.question_ids_json, []).map((value) => Number(value)).filter((value) => Number.isInteger(value) && value > 0) : [];
	if (!session || !questionIds.length) return regularQuestions || [];
	const { data: sourceQuestions, error: sourceError } = await db.from("questions").select("*").in("id", questionIds);
	if (sourceError) throw new Error(sourceError.message);
	const byId = new Map((sourceQuestions || []).map((question) => [Number(question.id), question]));
	return questionIds.map((questionId) => byId.get(questionId)).filter(Boolean).map((question, index) => ({
		...question,
		numero_questao: String(index + 1)
	}));
};
const answerQuestion = (questions, key) => {
	const byIdOrNumber = questions.find((question) => String(question.id || "") === key) || questions.find((question) => String(question.numero_questao || "") === key);
	if (byIdOrNumber) return byIdOrNumber;
	const ordinal = Number(key);
	return Number.isInteger(ordinal) && ordinal > 0 ? questions[ordinal - 1] : void 0;
};
const loadWrongQuestions = async (db, userId) => {
	const { data: attempts, error: attemptsError } = await db.from("exam_attempts").select("exam_id,answers_json").eq("user_id", userId);
	if (attemptsError) throw new Error(attemptsError.message);
	const examIds = [...new Set((attempts || []).map((attempt) => Number(attempt.exam_id)).filter(Boolean))];
	const questionLists = await Promise.all(examIds.map(async (examId) => [examId, await loadExamQuestions(db, examId)]));
	const questionsByExam = new Map(questionLists);
	const wrongBySubject = /* @__PURE__ */ new Map();
	const wrongQuestions = /* @__PURE__ */ new Map();
	for (const attempt of attempts || []) {
		const questions = questionsByExam.get(Number(attempt.exam_id)) || [];
		const answers = parseJson(attempt.answers_json, {});
		for (const [key, rawAnswer] of Object.entries(answers)) {
			const question = answerQuestion(questions, String(key));
			const correctAnswer = String(question?.correct_answer || "").trim().toUpperCase();
			const givenAnswer = String(rawAnswer || "").trim().toUpperCase();
			if (!question || !correctAnswer || correctAnswer === "X" || givenAnswer === correctAnswer) continue;
			const questionId = Number(question.id);
			if (!Number.isInteger(questionId) || questionId <= 0) continue;
			const subject = String(question.subject || "Geral");
			wrongQuestions.set(questionId, question);
			if (!wrongBySubject.has(subject)) wrongBySubject.set(subject, /* @__PURE__ */ new Set());
			wrongBySubject.get(subject).add(questionId);
		}
	}
	return {
		wrongBySubject,
		wrongQuestions
	};
};
const loadRanking = async (db, currentUser) => {
	const [{ data: users, error: usersError }, { data: attempts, error: attemptsError }] = await Promise.all([db.from("users").select("id,name,picture,supabase_auth_id"), db.from("exam_attempts").select("user_id,total,score")]);
	if (usersError || attemptsError) throw new Error(usersError?.message || attemptsError?.message || "Falha ao carregar ranking.");
	const totals = /* @__PURE__ */ new Map();
	for (const attempt of attempts || []) {
		const userId = Number(attempt.user_id);
		if (!Number.isInteger(userId) || userId <= 0) continue;
		const current = totals.get(userId) || {
			total: 0,
			correct: 0
		};
		current.total += Number(attempt.total || 0);
		current.correct += Number(attempt.score || 0);
		totals.set(userId, current);
	}
	return (await Promise.all((users || []).filter((user) => (totals.get(Number(user.id))?.total || 0) > 0).map(async (user) => {
		const userId = Number(user.id);
		const totalsForUser = totals.get(userId) || {
			total: 0,
			correct: 0
		};
		let identity;
		if (userId !== currentUser.id && !user.name && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(user.supabase_auth_id || ""))) {
			const { data, error } = await db.auth.admin.getUserById(user.supabase_auth_id);
			if (!error && data.user) identity = data.user;
		}
		return {
			...presentRankingUser(user, currentUser, identity),
			total_questions: totalsForUser.total,
			accuracy: totalsForUser.total ? Number((totalsForUser.correct * 100 / totalsForUser.total).toFixed(1)) : 0
		};
	}))).sort((left, right) => right.total_questions - left.total_questions || right.accuracy - left.accuracy);
};
const summaryPayload = (exam, questions, attempts) => {
	const scores = attempts.filter((attempt) => Number(attempt.exam_id) === Number(exam.id));
	const best = scores.length ? Math.max(...scores.map((attempt) => Number(attempt.percentage || 0))) : null;
	const last = scores.length ? Number(scores.sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || ""))).at(-1)?.percentage || 0) : null;
	return {
		id: Number(exam.id),
		title: String(exam.title || "Prova"),
		status: String(exam.status || "Pendente"),
		question_count: questions.length,
		best_score: best,
		last_score: last,
		attempt_count: scores.length,
		has_official_answers: Boolean(exam.has_official_answers),
		answer_key_source: String(exam.answer_key_source || "none"),
		gabarito_coverage: Number(exam.gabarito_coverage || 0),
		gabarito_summary: null,
		source_url: storedUrl(exam.source_url),
		gabarito_url: storedUrl(exam.gabarito_url)
	};
};
const loadLibrary = async (db, userId) => {
	const [links, owned, attempts] = await Promise.all([
		readAll(() => db.from("user_exams").select("exam_id").eq("user_id", userId).order("exam_id")),
		readAll(() => db.from("exams").select("id").eq("user_id", userId).order("id")),
		readAll(() => db.from("exam_attempts").select("*").eq("user_id", userId).order("id"))
	]);
	const ids = [.../* @__PURE__ */ new Set([...links.map((row) => Number(row.exam_id)), ...owned.map((row) => Number(row.id))])];
	if (!ids.length) return {
		ids,
		exams: [],
		questions: [],
		attempts,
		folders: [],
		sessions: []
	};
	const [exams, questions, sessions] = await Promise.all([
		readAll(() => db.from("exams").select("*").in("id", ids).order("id")),
		readAll(() => db.from("questions").select("*").in("exam_id", ids).order("question_index", {
			ascending: true,
			nullsFirst: false
		}).order("id")),
		readAll(() => db.from("generated_exam_sessions").select("*").in("exam_id", ids).order("exam_id"))
	]);
	const folderIds = [...new Set(exams.map((exam) => exam.folder_id).filter(Boolean))];
	return {
		ids,
		exams,
		questions,
		attempts,
		folders: folderIds.length ? await readAll(() => db.from("folders").select("*").in("id", folderIds).order("id")) : [],
		sessions
	};
};
const folderPayload = (library) => {
	const byExam = /* @__PURE__ */ new Map();
	for (const question of library.questions) {
		const examId = Number(question.exam_id);
		byExam.set(examId, [...byExam.get(examId) || [], question]);
	}
	const questionsById = new Map(library.questions.map((question) => [Number(question.id), question]));
	for (const session of library.sessions) {
		const ids = parseJson(session.question_ids_json, []).map(Number);
		byExam.set(Number(session.exam_id), ids.map((id) => questionsById.get(id)).filter(Boolean));
	}
	const summaries = library.exams.filter((exam) => !["Processando", "Erro"].includes(exam.status)).map((exam) => ({
		exam,
		questions: byExam.get(Number(exam.id)) || []
	})).map(({ exam, questions }) => summaryPayload(exam, questions, library.attempts));
	const folders = library.folders.map((folder) => ({
		id: Number(folder.id),
		name: String(folder.name || "Pasta"),
		exams: summaries.filter((exam) => Number(library.exams.find((row) => Number(row.id) === exam.id)?.folder_id) === Number(folder.id))
	}));
	const assigned = summaries.filter((exam) => !library.exams.find((row) => Number(row.id) === exam.id)?.folder_id);
	if (assigned.length) folders.unshift({
		id: "library",
		name: "Minhas provas",
		exams: assigned
	});
	return {
		folders,
		summaries,
		byExam
	};
};
const accessibleExam = async (db, userId, examId) => {
	const { data: link } = await db.from("user_exams").select("exam_id").eq("user_id", userId).eq("exam_id", examId).maybeSingle();
	if (link) return true;
	const { data: owned } = await db.from("exams").select("id").eq("id", examId).eq("user_id", userId).maybeSingle();
	return Boolean(owned);
};
const reusableExams = async (db, userId, urls) => {
	const eligible = [...new Set(urls)].filter(isPublicSourceUrl).slice(0, 50);
	if (!eligible.length) return {};
	const keys = await Promise.all(eligible.map(sourceKey));
	const ownedKeys = await Promise.all(eligible.map((url) => ownedSourceKey(userId, url)));
	const normalized = eligible.map(normalizeSourceUrl);
	const { data: aliases, error: aliasError } = await db.from("exam_sources").select("source_key,exam_id").in("source_key", [...keys, ...ownedKeys]);
	if (aliasError) throw new Error(aliasError.message);
	const { data: legacy, error: legacyError } = await db.from("exams").select("id,source_url").in("source_url", [.../* @__PURE__ */ new Set([...eligible, ...normalized])]).eq("status", "Aprovada");
	if (legacyError) throw new Error(legacyError.message);
	const ids = [.../* @__PURE__ */ new Set([...(aliases || []).map((row) => Number(row.exam_id)), ...(legacy || []).map((row) => Number(row.id))])];
	if (!ids.length) return {};
	const { data: exams, error } = await db.from("exams").select("id,title,status,doc_type,user_id").in("id", ids).eq("status", "Aprovada");
	if (error) throw new Error(error.message);
	const { data: catalog, error: catalogError } = await db.from("exam_catalog").select("source_url").in("source_url", [.../* @__PURE__ */ new Set([...eligible, ...normalized])]);
	if (catalogError) throw new Error(catalogError.message);
	const catalogUrls = new Set((catalog || []).map((row) => normalizeSourceUrl(row.source_url)));
	const result = {};
	for (const [index, url] of eligible.entries()) {
		const id = (aliases || []).find((row) => row.source_key === ownedKeys[index])?.exam_id || (aliases || []).find((row) => row.source_key === keys[index])?.exam_id || (legacy || []).find((row) => normalizeSourceUrl(row.source_url) === normalized[index])?.id;
		const exam = (exams || []).find((row) => Number(row.id) === Number(id));
		if (!exam || exam.doc_type === "generated_session") continue;
		if (!catalogUrls.has(normalized[index]) && !await accessibleExam(db, userId, Number(exam.id))) continue;
		const { count, error: countError } = await db.from("questions").select("id", {
			count: "exact",
			head: true
		}).eq("exam_id", exam.id);
		if (countError) throw new Error(countError.message);
		if (!count || count < 5) continue;
		result[url] = {
			id: Number(exam.id),
			title: String(exam.title || "Prova")
		};
	}
	return result;
};
const examDetail = async (db, examId) => {
	const { data: exam, error: examError } = await db.from("exams").select("*").eq("id", examId).single();
	if (examError || !exam) throw new Error(examError?.message || "Prova não encontrada.");
	const questions = await loadExamQuestions(db, examId);
	return {
		id: Number(exam.id),
		title: String(exam.title || "Prova"),
		status: String(exam.status || "Pendente"),
		folder_id: exam.folder_id === null ? null : Number(exam.folder_id),
		source_url: storedUrl(exam.source_url),
		gabarito_url: storedUrl(exam.gabarito_url),
		has_official_answers: Boolean(exam.has_official_answers),
		gabarito_coverage: Number(exam.gabarito_coverage || 0),
		gabarito_text: exam.gabarito_text || null,
		questions: (questions || []).map(questionPayload)
	};
};
const routePath = (request) => {
	const path = new URL(request.url).pathname;
	const index = path.indexOf("/app-gateway/");
	return (index >= 0 ? path.slice(index + 13) : path.replace(/^\/+/, "")).replace(/^\/+/, "");
};
const notSupported = (message) => json({ error: message }, 501);
Deno.serve(async (request) => {
	if (request.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
	try {
		const path = routePath(request);
		if (path === "api/v1/auth/config" && request.method === "GET") return json({
			google_enabled: Boolean(supabaseUrl && anonKey),
			supabase_enabled: Boolean(supabaseUrl && anonKey)
		});
		const { authUser, db } = await authenticate(request);
		const internalUser = await ensureInternalUser(db, authUser);
		if (path === "api/v1/auth/me" && request.method === "GET") return json({
			id: internalUser.id,
			email: internalUser.email,
			name: internalUser.name || "Concurseiro",
			picture: internalUser.picture || "",
			is_authenticated: true
		});
		if (path === "api/v1/auth/logout" && request.method === "POST") return json({ ok: true });
		if (path === "api/v1/exams/reuse-lookup" && request.method === "POST") {
			const payload = await request.json();
			if (!Array.isArray(payload.urls) || payload.urls.length > 50 || payload.urls.some((value) => typeof value !== "string" || value.length > 2e3)) return json({ error: "Informe até 50 fontes válidas." }, 400);
			return json(await reusableExams(db, internalUser.id, payload.urls));
		}
		if (path === "api/v1/auth/me" && request.method === "DELETE") {
			const { error } = await db.from("users").delete().eq("id", internalUser.id);
			if (error) return json({ error: error.message }, 400);
			return json({ ok: true });
		}
		if (path === "api/v1/exams/import-local" && request.method === "POST") try {
			return json(await importProcessedExam(db, internalUser.id, await request.json(), importedMedia));
		} catch (error) {
			if (error instanceof ImportError) return json({ error: error.message }, error.status);
			throw error;
		}
		if (path === "api/v1/search/catalog" && request.method === "POST") {
			const payload = await request.json();
			if (!Array.isArray(payload.items) || payload.items.length > 50) return json({ error: "Informe até 50 resultados de busca." }, 400);
			const sources = /* @__PURE__ */ new Map();
			for (const item of payload.items) {
				if (!isPublicSourceUrl(item.url) || item.url.length > 500) continue;
				const source_url = normalizeSourceUrl(item.url);
				sources.set(source_url, {
					source_url,
					title: String(item.title || "Prova de concurso").slice(0, 300),
					query_key: String(payload.query || "").slice(0, 100),
					gabarito_url: isPublicSourceUrl(item.gabarito_url) ? item.gabarito_url : null,
					match_score: Number(item.match_score || 0),
					source: String(item.source || "web").slice(0, 50),
					created_at: nowIso()
				});
			}
			if (sources.size) {
				const { error } = await db.from("exam_catalog").upsert([...sources.values()], {
					onConflict: "source_url",
					ignoreDuplicates: true
				});
				if (error) throw new Error(error.message);
			}
			return json({ saved: sources.size });
		}
		const library = await loadLibrary(db, internalUser.id);
		const shaped = folderPayload(library);
		if (path === "api/v1/folders" && request.method === "GET") return json(shaped.folders);
		if (path === "api/v1/library/snapshot" && request.method === "GET") {
			const manifests = {};
			for (const exam of library.exams) {
				const questions = shaped.byExam.get(Number(exam.id)) || [];
				const assets = /* @__PURE__ */ new Map();
				for (const question of questions) for (const [slot, values] of [["question", parseJson(question.images, [])], ...Object.entries(parseJson(question.option_images, {})).map(([key, images]) => [`option:${key}`, Array.isArray(images) ? images : []])]) values.forEach((value, index) => {
					const filename = String(value || "").split("/").pop() || `asset-${index}`;
					const current = assets.get(filename) || {
						filename,
						refs: []
					};
					current.refs.push({
						question_id: Number(question.id),
						slot,
						index,
						option_key: slot.startsWith("option:") ? slot.slice(7) : null
					});
					assets.set(filename, current);
				});
				manifests[String(exam.id)] = {
					exam_id: Number(exam.id),
					manifest_id: `exam:${exam.id}`,
					assets: [...assets.values()].map((asset) => ({
						asset_id: `questions/${asset.filename}`,
						filename: asset.filename,
						media_url: mediaUrl(`questions/${asset.filename}`),
						size: null,
						content_type: "image/*",
						available: true,
						references: asset.refs
					}))
				};
			}
			return json({
				schema_version: 1,
				user_id: internalUser.id,
				generated_at: nowIso(),
				library_version: nowIso(),
				folders: shaped.folders,
				exams: shaped.summaries,
				asset_manifests: manifests
			});
		}
		const examMatch = path.match(/^api\/v1\/exams\/(\d+)(?:\/(.*))?$/);
		if (examMatch) {
			const examId = Number(examMatch[1]);
			const suffix = examMatch[2] || "";
			let canAccess = await accessibleExam(db, internalUser.id, examId);
			if (!canAccess && suffix === "claim" && request.method === "POST") {
				const { data: aliases, error: aliasError } = await db.from("exam_sources").select("source_url").eq("exam_id", examId);
				if (aliasError) throw new Error(aliasError.message);
				const { data: original } = await db.from("exams").select("source_url").eq("id", examId).single();
				const reusable = await reusableExams(db, internalUser.id, [...(aliases || []).map((row) => String(row.source_url)), String(original?.source_url || "")]);
				canAccess = Object.values(reusable).some((exam) => exam.id === examId);
			}
			if (!canAccess) return json({ error: "Prova não atribuída à sua conta." }, 403);
			if (!suffix && request.method === "GET") return json(await examDetail(db, examId));
			if (suffix === "progress" && request.method === "GET") {
				const { data: exam } = await db.from("exams").select("status,progress,progress_message,error_type").eq("id", examId).single();
				return json({
					status: exam?.status || "Pendente",
					progress: Number(exam?.progress || 0),
					message: exam?.progress_message || "Pendente",
					error_type: exam?.error_type || null
				});
			}
			if (suffix === "claim" && request.method === "POST") {
				const { error } = await db.from("user_exams").upsert({
					user_id: internalUser.id,
					exam_id: examId,
					created_at: nowIso()
				}, { onConflict: "user_id,exam_id" });
				if (error) return json({ error: error.message }, 400);
				const exam = await examDetail(db, examId);
				return json({
					exam_id: exam.id,
					title: exam.title,
					status: exam.status,
					progress: 100,
					message: "Prova adicionada à biblioteca.",
					reused: true,
					already_in_library: true
				});
			}
			if (suffix.startsWith("media/") || suffix.startsWith("pdf/")) return notSupported("A mídia é servida pelo media-gateway do Supabase.");
		}
		if (path === "api/v1/exams/attempt" && request.method === "POST") {
			const payload = await request.json();
			const examId = Number(payload.exam_id || 0);
			if (!await accessibleExam(db, internalUser.id, examId)) return json({ error: "Prova não atribuída à sua conta." }, 403);
			const detail = await examDetail(db, examId);
			if (!payload.answers || typeof payload.answers !== "object" || Array.isArray(payload.answers)) return json({ error: "Informe as respostas da prova." }, 400);
			const elapsed = Number(payload.elapsed_seconds || 0);
			if (!Number.isInteger(elapsed) || elapsed < 0) return json({ error: "O tempo de estudo é inválido." }, 400);
			const result = gradeAttempt(detail.questions, payload.answers);
			const { data: attempt, error } = await db.from("exam_attempts").insert({
				exam_id: examId,
				score: result.score,
				total: result.total,
				percentage: result.percentage,
				elapsed_seconds: elapsed,
				answers_json: JSON.stringify(payload.answers),
				created_at: nowIso(),
				user_id: internalUser.id
			}).select("id").single();
			if (error) return json({ error: error.message }, 400);
			return json({
				attempt_id: Number(attempt.id),
				exam_id: examId,
				...result,
				elapsed_seconds: elapsed
			});
		}
		if (path === "api/v1/stats/overview" && request.method === "GET") {
			const rankIndex = (await loadRanking(db, internalUser)).findIndex((entry) => entry.id === internalUser.id);
			return json({
				...studyOverview(library.attempts),
				rank: rankIndex >= 0 ? `${rankIndex + 1}º` : "—"
			});
		}
		if (path === "api/v1/ranking" && request.method === "GET") {
			const ranking = await loadRanking(db, internalUser);
			return json(ranking.map(({ id: _id, ...entry }) => entry));
		}
		if (path === "api/v1/downloads/active" && request.method === "GET") return json([]);
		if (path === "api/v1/notebook/stats" && request.method === "GET") {
			const { wrongBySubject } = await loadWrongQuestions(db, internalUser.id);
			return json([...wrongBySubject.entries()].map(([subject, questionIds]) => ({
				subject,
				count: questionIds.size
			})).sort((left, right) => right.count - left.count || left.subject.localeCompare(right.subject)));
		}
		if (path === "api/v1/notebook" && request.method === "GET") {
			const subject = new URL(request.url).searchParams.get("subject")?.trim() || "";
			const { wrongQuestions } = await loadWrongQuestions(db, internalUser.id);
			const questions = [...wrongQuestions.values()].filter((question) => !subject || String(question.subject || "Geral") === subject).sort((left, right) => Number(left.id) - Number(right.id)).slice(0, 100);
			const title = `Caderno de Erros Inteligente${subject ? ` - ${subject}` : " (Todas as Materias)"}`;
			const { data: created, error: createError } = await db.from("exams").insert({
				title,
				status: "Sessao",
				user_id: internalUser.id,
				has_official_answers: 1,
				answer_key_source: "generated",
				doc_type: "generated_session",
				gabarito_coverage: 100,
				progress: 100,
				progress_message: "Caderno pronto"
			}).select("id").single();
			if (createError || !created) return json({ error: createError?.message || "Nao foi possivel criar o caderno." }, 400);
			const questionIds = questions.map((question) => Number(question.id));
			const { error: sessionError } = await db.from("generated_exam_sessions").insert({
				exam_id: created.id,
				kind: "notebook",
				question_ids_json: JSON.stringify(questionIds),
				created_at: nowIso()
			});
			if (sessionError) return json({ error: sessionError.message }, 400);
			const { error: linkError } = await db.from("user_exams").upsert({
				user_id: internalUser.id,
				exam_id: Number(created.id),
				created_at: nowIso()
			}, { onConflict: "user_id,exam_id" });
			if (linkError) return json({ error: linkError.message }, 400);
			return json({
				id: Number(created.id),
				title,
				status: "Sessao",
				folder_id: null,
				source_url: null,
				gabarito_url: null,
				has_official_answers: true,
				gabarito_coverage: 100,
				gabarito_text: null,
				questions: questions.map((question, index) => questionPayload({
					...question,
					numero_questao: String(index + 1)
				}))
			});
		}
		if (path === "api/v1/custom-simulations/options" && request.method === "GET") {
			const subjects = /* @__PURE__ */ new Map();
			const sources = /* @__PURE__ */ new Map();
			for (const question of library.questions) {
				const subject = String(question.subject || "Geral");
				subjects.set(subject, (subjects.get(subject) || 0) + 1);
				const examId = Number(question.exam_id);
				const exam = library.exams.find((row) => Number(row.id) === examId);
				if (exam) sources.set(examId, {
					title: String(exam.title || "Prova"),
					count: (sources.get(examId)?.count || 0) + 1
				});
			}
			return json({
				available_questions: library.questions.length,
				subjects: [...subjects].map(([name, count]) => ({
					name,
					count
				})),
				sources: [...sources].map(([id, value]) => ({
					id,
					...value
				}))
			});
		}
		if (path === "api/v1/custom-simulations" && request.method === "GET") return json(library.sessions.filter((session) => session.kind === "custom").map((session) => {
			const summary = shaped.summaries.find((row) => row.id === Number(session.exam_id));
			return {
				...summary,
				id: Number(session.exam_id),
				title: summary?.title || "Simulado personalizado",
				kind: "custom",
				created_at: session.created_at
			};
		}));
		if (path === "api/v1/exams/generate_custom" && request.method === "POST") {
			const url = new URL(request.url);
			const count = Number(url.searchParams.get("count") || 20);
			if (!Number.isInteger(count) || count < 5 || count > 100) return json({ error: "Escolha de 5 a 100 questões." }, 400);
			const subjects = new Set(url.searchParams.getAll("subjects").map((value) => value.trim()).filter(Boolean));
			const sourceId = Number(url.searchParams.get("source_exam_id") || 0);
			const eligible = library.questions.filter((question) => Object.keys(parseJson(question.options, {})).length >= 2 && String(question.correct_answer || "").trim() && (!subjects.size || subjects.has(String(question.subject || "Geral"))) && (!sourceId || Number(question.exam_id) === sourceId));
			if (!eligible.length) return json({ error: "Nenhuma questão válida para os filtros escolhidos." }, 400);
			if (url.searchParams.get("strict") === "true" && eligible.length < count) return json({ error: `Há apenas ${eligible.length} questões válidas para os filtros escolhidos; reduza a quantidade ou amplie a seleção.` }, 400);
			for (let index = eligible.length - 1; index > 0; index--) {
				const target = Math.floor(Math.random() * (index + 1));
				[eligible[index], eligible[target]] = [eligible[target], eligible[index]];
			}
			const candidates = eligible.slice(0, count);
			const { data: created, error: createError } = await db.from("exams").insert({
				title: "Simulado personalizado",
				status: "Sessão",
				user_id: internalUser.id,
				has_official_answers: 1,
				answer_key_source: "generated",
				doc_type: "generated_session",
				gabarito_coverage: 100,
				progress: 100,
				progress_message: "Sessão pronta"
			}).select("id").single();
			if (createError || !created) return json({ error: createError?.message || "Não foi possível criar o simulado." }, 400);
			const { error: sessionError } = await db.from("generated_exam_sessions").insert({
				exam_id: created.id,
				kind: "custom",
				question_ids_json: JSON.stringify(candidates.map((question) => question.id)),
				created_at: nowIso()
			});
			if (sessionError) return json({ error: sessionError.message }, 400);
			const { error: linkError } = await db.from("user_exams").upsert({
				user_id: internalUser.id,
				exam_id: Number(created.id),
				created_at: nowIso()
			}, { onConflict: "user_id,exam_id" });
			if (linkError) return json({ error: linkError.message }, 400);
			return json({
				id: Number(created.id),
				title: "Simulado personalizado",
				status: "Sessão",
				has_official_answers: true,
				gabarito_coverage: 100,
				questions: candidates.map((question, index) => questionPayload({
					...question,
					numero_questao: String(index + 1)
				}))
			});
		}
		if (path === "api/v1/search" && request.method === "GET") {
			const url = new URL(request.url);
			const query = (url.searchParams.get("q") || "").trim();
			const page = Math.max(1, Number(url.searchParams.get("page") || 1));
			const pageSize = Math.min(50, Math.max(1, Number(url.searchParams.get("page_size") || 25)));
			const pattern = `%${query.replaceAll("%", "\\%").replaceAll("_", "\\_")}%`;
			const { data: cards, error } = await db.from("exam_catalog").select("id,title,source_url,gabarito_url,match_score,source").or(`title.ilike.${pattern},source_url.ilike.${pattern}`).order("match_score", { ascending: false }).limit(200);
			if (error) return json({ error: error.message }, 400);
			const items = (cards || []).map((card) => ({
				id: card.id,
				title: card.title,
				url: card.source_url,
				gabarito_url: card.gabarito_url,
				has_gabarito_link: Boolean(card.gabarito_url),
				match_score: Number(card.match_score || 0),
				source: card.source || "web",
				status: "Pendente",
				reuse_available: false
			}));
			const start = (page - 1) * pageSize;
			return json({
				items: items.slice(start, start + pageSize),
				page,
				page_size: pageSize,
				total: items.length,
				total_pages: Math.ceil(items.length / pageSize),
				has_previous: page > 1,
				has_next: start + pageSize < items.length
			});
		}
		if (path === "api/v1/exams/ingest" && request.method === "POST") return notSupported("A extração/OCR continua local no aplicativo; importe o PDF ou JSON extraído.");
		return json({ error: "Rota Supabase não encontrada." }, 404);
	} catch (error) {
		if (error instanceof Response) return error;
		console.error("app-gateway error", error);
		return json({ error: error instanceof Error ? error.message : "Falha inesperada no gateway Supabase." }, 500);
	}
});
//#endregion
