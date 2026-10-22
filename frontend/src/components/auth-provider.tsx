"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  ApiError,
  GENERIC_LOGIN_ERROR,
  getCurrentUserRequest,
  loginRequest,
  type UserPublic,
} from "@/lib/api";

export type AuthStatus =
  | "loading"
  | "unauthenticated"
  | "authenticated"
  | "error";

interface AuthContextValue {
  status: AuthStatus;
  user: UserPublic | null;
  /** Present only while authenticated; kept in memory, not browser storage. */
  accessToken: string | null;
  errorMessage: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
  /** Reload `/users/me` into context after a profile update. */
  refreshUser: () => Promise<UserPublic | null>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // Memory-only session: a full page refresh clears the token (by design).
  const tokenRef = useRef<string | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserPublic | null>(null);
  const [status, setStatus] = useState<AuthStatus>("unauthenticated");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const clearSession = useCallback(() => {
    tokenRef.current = null;
    setAccessToken(null);
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const logout = useCallback(() => {
    // Backend JWT revocation is not implemented; logout clears the browser session only.
    clearSession();
    setErrorMessage(null);
  }, [clearSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      setStatus("loading");
      setErrorMessage(null);
      try {
        const loginResult = await loginRequest(email.trim(), password);
        const token = loginResult.access_token;
        tokenRef.current = token;
        setAccessToken(token);

        const profile = await getCurrentUserRequest(token);
        if (!profile.is_active) {
          clearSession();
          setErrorMessage(GENERIC_LOGIN_ERROR);
          setStatus("unauthenticated");
          return;
        }
        setUser(profile);
        setStatus("authenticated");
      } catch (error) {
        clearSession();
        if (error instanceof ApiError) {
          if (error.status === 401) {
            setErrorMessage(GENERIC_LOGIN_ERROR);
          } else if (error.status === 0) {
            setErrorMessage(error.detail);
          } else {
            setErrorMessage(
              "Sign-in is temporarily unavailable. Try again shortly.",
            );
          }
        } else {
          setErrorMessage(
            "Sign-in is temporarily unavailable. Try again shortly.",
          );
        }
        setStatus("unauthenticated");
      }
    },
    [clearSession],
  );

  const clearError = useCallback(() => {
    setErrorMessage(null);
  }, []);

  const refreshUser = useCallback(async () => {
    const token = tokenRef.current;
    if (!token) return null;
    const profile = await getCurrentUserRequest(token);
    setUser(profile);
    return profile;
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      accessToken,
      errorMessage,
      login,
      logout,
      clearError,
      refreshUser,
    }),
    [
      status,
      user,
      accessToken,
      errorMessage,
      login,
      logout,
      clearError,
      refreshUser,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

/** Clear session when a protected API call reports an invalid/expired token. */
export function useHandleUnauthorized() {
  const { logout } = useAuth();
  return useCallback(
    (error: unknown) => {
      if (error instanceof ApiError && error.status === 401) {
        logout();
        return true;
      }
      return false;
    },
    [logout],
  );
}
