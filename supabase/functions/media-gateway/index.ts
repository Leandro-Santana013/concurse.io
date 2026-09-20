import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, range",
  "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS, PUT",
  "Access-Control-Allow-Origin": Deno.env.get("MEDIA_CORS_ORIGIN") || "*",
  "Vary": "Origin",
};

const json = (body: Record<string, unknown>, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json; charset=utf-8" },
  });

const authHeader = (request: Request) => request.headers.get("Authorization") || "";

const validObjectPath = (value: string) => {
  if (!value || value.length > 512 || value.startsWith("/") || value.includes("\\")) return false;
  if (value.split("/").some((segment) => !segment || segment === "." || segment === "..")) return false;
  if ([...value].some((char) => char.charCodeAt(0) < 0x20 || char.charCodeAt(0) === 0x7f)) return false;
  const prefixes = (Deno.env.get("OCI_MEDIA_ALLOWED_PREFIXES") || "questions/,exams/")
    .split(",")
    .map((prefix) => prefix.trim().replace(/^\/+|\/+$/g, ""))
    .filter(Boolean);
  return prefixes.length === 0 || prefixes.some((prefix) => value === prefix || value.startsWith(`${prefix}/`));
};

const encodedPath = (value: string) => value.split("/").map(encodeURIComponent).join("/");

const parObjectUrl = (base: string, objectPath: string) => {
  const normalized = base.replace(/\/+$/, "");
  return `${normalized}/${encodedPath(objectPath)}`;
};

const forwardHeaders = (response: Response) => {
  const headers = new Headers(corsHeaders);
  for (const name of ["accept-ranges", "cache-control", "content-disposition", "content-length", "content-range", "content-type", "etag", "last-modified"]) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
};

const getAuthenticatedUser = async (request: Request) => {
  const token = authHeader(request);
  if (!token.toLowerCase().startsWith("bearer ")) return null;
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const supabaseKey = Deno.env.get("SUPABASE_ANON_KEY") || Deno.env.get("SUPABASE_PUBLISHABLE_KEY");
  if (!supabaseUrl || !supabaseKey) throw new Error("Supabase Auth não está configurado na função.");
  const supabase = createClient(supabaseUrl, supabaseKey, {
    global: { headers: { Authorization: token } },
  });
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) return null;
  return data.user;
};

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  let user;
  try {
    user = await getAuthenticatedUser(request);
  } catch (error) {
    console.error("media-gateway auth configuration error", error);
    return json({ error: "A autenticação do Supabase não está configurada." }, 500);
  }
  if (!user) return json({ error: "É necessário estar autenticado." }, 401);

  const url = new URL(request.url);
  const objectPath = url.searchParams.get("path") || url.pathname.split("/media-gateway/")[1] || "";
  if (!validObjectPath(objectPath)) return json({ error: "Caminho de mídia inválido." }, 400);

  const isWrite = request.method === "PUT";
  const parBase = isWrite
    ? Deno.env.get("OCI_MEDIA_WRITE_PAR_URL")
    : Deno.env.get("OCI_MEDIA_READ_PAR_URL");
  if (!parBase) {
    return json({ error: isWrite ? "Upload de mídia não está configurado." : "Leitura de mídia não está configurada." }, 503);
  }

  const upstreamHeaders = new Headers();
  for (const name of ["content-type", "content-length", "if-match", "if-none-match", "range"]) {
    const value = request.headers.get(name);
    if (value) upstreamHeaders.set(name, value);
  }
  const upstream = await fetch(parObjectUrl(parBase, objectPath), {
    method: isWrite ? "PUT" : request.method,
    headers: upstreamHeaders,
    body: isWrite ? request.body : undefined,
  });

  if (!upstream.ok && upstream.status !== 206) {
    console.error("media-gateway upstream error", { status: upstream.status, objectPath, userId: user.id });
  }
  return new Response(isWrite ? await upstream.text() : upstream.body, {
    status: upstream.status,
    headers: isWrite ? { ...corsHeaders, "Content-Type": upstream.headers.get("content-type") || "application/json" } : forwardHeaders(upstream),
  });
});
