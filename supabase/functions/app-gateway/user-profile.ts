export type StoredUser = {
  id: number;
  email?: string | null;
  name?: string | null;
  picture?: string | null;
  supabase_auth_id?: string | null;
};

export type AuthIdentity = {
  id: string;
  email?: string | null;
  user_metadata?: Record<string, unknown>;
};

export type InternalUser = {
  id: number;
  email: string;
  name: string;
  picture: string;
  supabase_auth_id: string;
};

const visibleText = (value: unknown): string => {
  const text = String(value || "").trim();
  return /^(enc|hmac):v1:/.test(text) ? "" : text;
};

export const presentInternalUser = (stored: StoredUser, identity: AuthIdentity): InternalUser => {
  const metadata = identity.user_metadata || {};
  const legacyEmail = visibleText(stored.email);
  // The legacy fields can be empty or pseudonymous after encryption. The
  // verified Auth identity supplies presentation only; ownership stays on id.
  return {
    id: Number(stored.id),
    supabase_auth_id: String(stored.supabase_auth_id || identity.id),
    email: visibleText(identity.email) || (/@users\.invalid$/i.test(legacyEmail) ? "" : legacyEmail),
    name: visibleText(metadata.full_name) || visibleText(metadata.name) || visibleText(stored.name) || "Concurseiro",
    picture: visibleText(metadata.avatar_url) || visibleText(metadata.picture) || visibleText(stored.picture),
  };
};

export const presentRankingUser = (stored: StoredUser, currentUser: InternalUser, identity?: AuthIdentity) => {
  const metadata = identity?.user_metadata || {};
  const isCurrentUser = Number(stored.id) === Number(currentUser.id);
  return {
    id: Number(stored.id),
    name: (isCurrentUser ? currentUser.name : "") || visibleText(metadata.full_name) || visibleText(metadata.name) || visibleText(stored.name) || "Concurseiro",
    picture: (isCurrentUser ? currentUser.picture : "") || visibleText(metadata.avatar_url) || visibleText(metadata.picture) || visibleText(stored.picture),
  };
};
