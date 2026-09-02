export interface AuthUser {
  id: number;
  email: string;
  name: string;
  picture: string;
  is_authenticated: boolean;
}

export interface AuthConfig {
  google_enabled: boolean;
}
