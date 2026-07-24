import {HttpClient, HttpHeaders} from '@angular/common/http';
import {Injectable, computed, inject, signal} from '@angular/core';
import { Router } from '@angular/router';
import {firstValueFrom} from 'rxjs';

export type UserRole = 'pm' | 'candidate' | null;
type BackendRole = 'PROJECT_MANAGER' | 'CANDIDATE';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatar?: string;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  expires_in_seconds: number;
}

interface OTPDispatchResponse {
  flow: 'signup' | 'login';
  message: string;
  expires_in_seconds: number;
}

interface AuthSessionResponse {
  user_id: string;
  email: string;
  role: BackendRole | string;
  flow: 'signup' | 'login';
  auth_stage: string;
  is_authenticated: boolean;
  face_registered: boolean;
  can_register_face: boolean;
  requires_face_verification: boolean;
  next_step: string;
  token: TokenResponse;
  face_similarity_threshold: number | null;
}

interface FaceRegistrationResponse {
  user_id: string;
  face_registered: boolean;
  auth_stage: string;
  is_authenticated: boolean;
  next_step: string;
  token: TokenResponse;
  message: string;
}

interface FaceVerificationResponse {
  success: boolean;
  status: string;
  similarity_score: number | null;
  threshold: number;
  remaining_attempts: number;
  auth_stage: string;
  is_authenticated: boolean;
  next_step: string;
  token: TokenResponse | null;
}

export interface CandidateAccessValidationResult {
  valid: boolean;
  candidate_email: string | null;
  schedule_status: string | null;
  job_id: string | null;
  schedule_id: string | null;
  slot_id: string | null;
}

interface StoredAuthState {
  user: User | null;
  authStage: string | null;
  nextStep: string | null;
  accessToken: string | null;
  pendingToken: string | null;
  faceRegistered: boolean;
}

type DisplayNameByEmail = Record<string, string>;

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);
  private readonly storageKey = 'talentos.auth.session';
  private readonly displayNameStorageKey = 'talentos.auth.displayNames';
  private readonly postAuthRedirectStorageKey = 'talentos.auth.postLoginRedirect';
  private readonly authBaseUrl = this.resolveAuthBaseUrl();
  private displayNameByEmail = this.restoreDisplayNames();

  currentUser = signal<User | null>(null);
  authStage = signal<string | null>(null);
  nextStep = signal<string | null>(null);
  accessToken = signal<string | null>(null);
  pendingToken = signal<string | null>(null);
  faceRegistered = signal(false);
  loading = signal(false);
  errorMessage = signal<string | null>(null);

  isAuthenticated = computed(
    () =>
      this.authStage() === 'authenticated'
      && !!this.currentUser()
      && !!this.accessToken(),
  );

  constructor() {
    this.restoreSession();
  }

  async sendSignupOtp(
    email: string,
    role: UserRole,
    displayName?: string,
    invitationToken?: string | null,
  ): Promise<OTPDispatchResponse> {
    this.errorMessage.set(null);
    const backendRole = this.toBackendRole(role);
    if (!backendRole) {
      throw new Error('Role is required for sign-up.');
    }

    this.rememberDisplayNameForEmail(email, displayName);

    this.loading.set(true);
    try {
      const response = await firstValueFrom(
        this.http.post<OTPDispatchResponse>(
          `${this.authBaseUrl}/auth/signup/send-otp`,
          {
            email,
            role: backendRole,
            invitation_token: invitationToken?.trim() || undefined,
          },
        ),
      );
      return response;
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to send sign-up OTP.');
      this.errorMessage.set(message);
      throw new Error(message);
    } finally {
      this.loading.set(false);
    }
  }

  async verifySignupOtp(
    email: string,
    role: UserRole,
    otpCode: string,
    displayName?: string,
    invitationToken?: string | null,
  ): Promise<void> {
    this.rememberDisplayNameForEmail(email, displayName);
    await this.verifyOtpFlow({
      endpoint: '/auth/signup/verify-otp',
      email,
      role,
      otpCode,
      invitationToken,
    });
  }

  async sendLoginOtp(email: string, role: UserRole, invitationToken?: string | null): Promise<OTPDispatchResponse> {
    this.errorMessage.set(null);
    const backendRole = this.toBackendRole(role);
    if (!backendRole) {
      throw new Error('Role is required for login.');
    }

    this.loading.set(true);
    try {
      const response = await firstValueFrom(
        this.http.post<OTPDispatchResponse>(
          `${this.authBaseUrl}/auth/login/send-otp`,
          {
            email,
            role: backendRole,
            invitation_token: invitationToken?.trim() || undefined,
          },
        ),
      );
      return response;
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to send login OTP.');
      this.errorMessage.set(message);
      throw new Error(message);
    } finally {
      this.loading.set(false);
    }
  }

  async verifyLoginOtp(
    email: string,
    role: UserRole,
    otpCode: string,
    invitationToken?: string | null,
  ): Promise<void> {
    await this.verifyOtpFlow({
      endpoint: '/auth/login/verify-otp',
      email,
      role,
      otpCode,
      invitationToken,
    });
  }

  async registerFace(file: File): Promise<void> {
    const token = this.pendingToken();
    if (!token) {
      throw new Error('No pending auth session found for face registration.');
    }

    this.loading.set(true);
    this.errorMessage.set(null);

    const formData = new FormData();
    formData.append('image', file);

    try {
      const response = await firstValueFrom(
        this.http.post<FaceRegistrationResponse>(
          `${this.authBaseUrl}/candidate/register-face`,
          formData,
          {
            headers: new HttpHeaders({
              Authorization: `Bearer ${token}`,
            }),
          },
        ),
      );

      const currentUser = this.currentUser();
      if (!currentUser) {
        throw new Error('Candidate user details are missing in auth state.');
      }

      this.currentUser.set({...currentUser, role: 'candidate'});
      this.authStage.set(response.auth_stage);
      this.nextStep.set(response.next_step);
      this.faceRegistered.set(response.face_registered);
      this.pendingToken.set(null);
      this.accessToken.set(response.token.access_token);
      this.persistSession();
      await this.navigateAfterAuthState();
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Face registration failed.');
      this.errorMessage.set(message);
      throw new Error(message);
    } finally {
      this.loading.set(false);
    }
  }

  async verifyFace(file: File): Promise<void> {
    const token = this.pendingToken();
    if (!token) {
      throw new Error('No pending auth session found for face verification.');
    }

    this.loading.set(true);
    this.errorMessage.set(null);

    const formData = new FormData();
    formData.append('image', file);

    try {
      const response = await firstValueFrom(
        this.http.post<FaceVerificationResponse>(
          `${this.authBaseUrl}/candidate/verify-face`,
          formData,
          {
            headers: new HttpHeaders({
              Authorization: `Bearer ${token}`,
            }),
          },
        ),
      );

      if (!response.success || !response.token) {
        const warning = `Face verification failed. Remaining attempts: ${response.remaining_attempts}.`;
        this.errorMessage.set(warning);
        throw new Error(warning);
      }

      const currentUser = this.currentUser();
      if (!currentUser) {
        throw new Error('Candidate user details are missing in auth state.');
      }

      this.currentUser.set({...currentUser, role: 'candidate'});
      this.authStage.set(response.auth_stage);
      this.nextStep.set(response.next_step);
      this.pendingToken.set(null);
      this.accessToken.set(response.token.access_token);
      this.persistSession();
      await this.navigateAfterAuthState();
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Face verification failed.');
      this.errorMessage.set(message);
      throw new Error(message);
    } finally {
      this.loading.set(false);
    }
  }

  async validateCandidateAccessLink(payload: {
    email: string;
    invitationToken: string;
    flow: 'invite' | 'l0_session';
    scheduleId?: string | null;
    slotId?: string | null;
  }): Promise<CandidateAccessValidationResult> {
    this.errorMessage.set(null);

    try {
      return await firstValueFrom(
        this.http.post<CandidateAccessValidationResult>(
          `${this.authBaseUrl}/auth/candidate-access/validate`,
          {
            email: payload.email,
            invitation_token: payload.invitationToken,
            flow: payload.flow,
            schedule_id: payload.scheduleId?.trim() || undefined,
            slot_id: payload.slotId?.trim() || undefined,
          },
        ),
      );
    } catch (error) {
      const message = this.extractErrorMessage(error, 'Unable to validate candidate access link.');
      this.errorMessage.set(message);
      throw new Error(message);
    }
  }

  hasPendingStep(step: 'register_face' | 'verify_face'): boolean {
    return !!this.pendingToken() && this.nextStep() === step;
  }

  getAuthHeaders(options: {usePendingToken?: boolean} = {}): HttpHeaders {
    const token = options.usePendingToken ? this.pendingToken() : this.accessToken();
    if (!token) {
      return new HttpHeaders();
    }
    return new HttpHeaders({Authorization: `Bearer ${token}`});
  }

  async logout(redirectTo?: string | null): Promise<void> {
    const currentRole = this.currentUser()?.role;
    const nextRoute = redirectTo === undefined
      ? (currentRole === 'candidate' ? '/auth/candidate/login' : '/auth/login')
      : redirectTo;

    this.resetState();
    if (!nextRoute) {
      return;
    }

    await this.router.navigateByUrl(nextRoute, {replaceUrl: true});
  }

  setPostAuthRedirect(url: string | null): void {
    if (typeof localStorage === 'undefined') {
      return;
    }

    if (!url || !url.startsWith('/')) {
      localStorage.removeItem(this.postAuthRedirectStorageKey);
      return;
    }

    localStorage.setItem(this.postAuthRedirectStorageKey, url);
  }

  updateCurrentUserName(name: string): void {
    const currentUser = this.currentUser();
    if (!currentUser) {
      return;
    }

    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }

    this.currentUser.set({
      ...currentUser,
      name: trimmed,
    });
    this.rememberDisplayNameForEmail(currentUser.email, trimmed);
    this.persistSession();
  }

  private async verifyOtpFlow(options: {
    endpoint: '/auth/signup/verify-otp' | '/auth/login/verify-otp';
    email: string;
    role: UserRole;
    otpCode: string;
    invitationToken?: string | null;
  }): Promise<void> {
    this.errorMessage.set(null);
    const backendRole = this.toBackendRole(options.role);
    if (!backendRole) {
      throw new Error('Role is required for OTP verification.');
    }

    this.loading.set(true);
    try {
      const response = await firstValueFrom(
        this.http.post<AuthSessionResponse>(
          `${this.authBaseUrl}${options.endpoint}`,
          {
            email: options.email,
            role: backendRole,
            otp_code: options.otpCode,
            invitation_token: options.invitationToken?.trim() || undefined,
          },
        ),
      );

      const resolvedRole = this.fromBackendRole(response.role);
      if (!resolvedRole) {
        throw new Error('Unable to determine account role from authentication response.');
      }

      if (options.role && resolvedRole !== options.role) {
        throw new Error('Role mismatch detected. Use the correct role tab before verifying OTP.');
      }

      this.validateCandidateOtpStep(response, resolvedRole, options.endpoint);
      this.applyAuthSession(response, resolvedRole);
      await this.navigateAfterAuthState();
    } catch (error) {
      const message = this.extractErrorMessage(error, 'OTP verification failed.');
      this.errorMessage.set(message);
      throw new Error(message);
    } finally {
      this.loading.set(false);
    }
  }

  private applyAuthSession(session: AuthSessionResponse, role: Exclude<UserRole, null>): void {
    const user: User = {
      id: session.user_id,
      name: this.resolveUserName(session.email, role),
      email: session.email,
      role,
      avatar: this.avatarForEmail(session.email),
    };

    this.currentUser.set(user);
    this.authStage.set(session.auth_stage);
    this.nextStep.set(session.next_step);
    this.faceRegistered.set(session.face_registered);

    if (session.is_authenticated) {
      this.accessToken.set(session.token.access_token);
      this.pendingToken.set(null);
    } else {
      this.pendingToken.set(session.token.access_token);
      this.accessToken.set(null);
    }

    this.persistSession();
  }

  private async navigateAfterAuthState(): Promise<void> {
    if (this.isAuthenticated()) {
      const redirectPath = this.consumePostAuthRedirect();
      if (redirectPath) {
        await this.router.navigateByUrl(redirectPath, {replaceUrl: true});
        return;
      }

      await this.router.navigateByUrl(this.dashboardRouteForRole(this.currentUser()?.role ?? null), {replaceUrl: true});
      return;
    }

    const nextStep = this.nextStep();
    if (nextStep === 'register_face') {
      await this.router.navigate(['/auth/face-register']);
      return;
    }

    if (nextStep === 'verify_face') {
      await this.router.navigate(['/auth/face-verify']);
      return;
    }
  }

  private persistSession(): void {
    if (typeof localStorage === 'undefined') {
      return;
    }

    const payload: StoredAuthState = {
      user: this.currentUser(),
      authStage: this.authStage(),
      nextStep: this.nextStep(),
      accessToken: this.accessToken(),
      pendingToken: this.pendingToken(),
      faceRegistered: this.faceRegistered(),
    };
    localStorage.setItem(this.storageKey, JSON.stringify(payload));
  }

  private restoreSession(): void {
    if (typeof localStorage === 'undefined') {
      return;
    }

    const raw = localStorage.getItem(this.storageKey);
    if (!raw) {
      return;
    }

    try {
      const parsed = JSON.parse(raw) as StoredAuthState;
      const restoredUser = parsed.user
        ? {
            ...parsed.user,
            name: this.resolveUserName(parsed.user.email, parsed.user.role),
          }
        : null;
      this.currentUser.set(restoredUser);
      this.authStage.set(parsed.authStage);
      this.nextStep.set(parsed.nextStep);
      this.accessToken.set(parsed.accessToken);
      this.pendingToken.set(parsed.pendingToken);
      this.faceRegistered.set(parsed.faceRegistered ?? false);
    } catch {
      this.resetState();
    }
  }

  private resetState(): void {
    this.currentUser.set(null);
    this.authStage.set(null);
    this.nextStep.set(null);
    this.accessToken.set(null);
    this.pendingToken.set(null);
    this.faceRegistered.set(false);
    this.errorMessage.set(null);

    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem(this.storageKey);
      localStorage.removeItem(this.postAuthRedirectStorageKey);
    }
  }

  private consumePostAuthRedirect(): string | null {
    if (typeof localStorage === 'undefined') {
      return null;
    }

    const raw = localStorage.getItem(this.postAuthRedirectStorageKey);
    if (!raw || !raw.startsWith('/')) {
      localStorage.removeItem(this.postAuthRedirectStorageKey);
      return null;
    }

    localStorage.removeItem(this.postAuthRedirectStorageKey);
    return raw;
  }

  private resolveAuthBaseUrl(): string {
    const envValue = (globalThis as {AUTH_API_BASE_URL?: string}).AUTH_API_BASE_URL;
    if (envValue) {
      return envValue;
    }

    if (typeof localStorage !== 'undefined') {
      const persisted = localStorage.getItem('talentos.auth.baseUrl');
      if (persisted) {
        return persisted;
      }
    }
    return 'http://127.0.0.1:8000';
  }

  private toBackendRole(role: UserRole): BackendRole | null {
    switch (role) {
      case 'pm':
        return 'PROJECT_MANAGER';
      case 'candidate':
        return 'CANDIDATE';
      default:
        return null;
    }
  }

  private fromBackendRole(role: BackendRole | string): UserRole {
    const normalized = String(role ?? '').trim().toUpperCase();
    if (normalized === 'PROJECT_MANAGER' || normalized === 'PM' || normalized === 'MANAGER') {
      return 'pm';
    }
    if (normalized === 'CANDIDATE') {
      return 'candidate';
    }
    return null;
  }

  private validateCandidateOtpStep(
    session: AuthSessionResponse,
    resolvedRole: Exclude<UserRole, null>,
    endpoint: '/auth/signup/verify-otp' | '/auth/login/verify-otp',
  ): void {
    if (resolvedRole !== 'candidate') {
      return;
    }

    if (endpoint === '/auth/signup/verify-otp') {
      if (session.next_step !== 'register_face') {
        throw new Error('Candidate sign-up must continue to face registration after OTP verification.');
      }
      return;
    }

    const nextStep = session.next_step;
    if (nextStep !== 'verify_face' && nextStep !== 'register_face') {
      throw new Error('Candidate login must continue with face verification after OTP verification.');
    }
  }

  private dashboardRouteForRole(role: UserRole): string {
    if (role === 'pm') {
      return '/dashboard/manager';
    }
    if (role === 'candidate') {
      return '/exam';
    }
    return '/dashboard';
  }

  private defaultNameForRole(role: UserRole, email: string): string {
    if (role === 'pm') {
      return email.split('@')[0].replace(/[._-]/g, ' ').trim() || 'Manager';
    }
    if (role === 'candidate') {
      return email.split('@')[0].replace(/[._-]/g, ' ').trim() || 'Candidate';
    }
    return 'User';
  }

  private resolveUserName(email: string, role: UserRole): string {
    const storedName = this.getDisplayNameForEmail(email);
    if (storedName) {
      return storedName;
    }
    return this.defaultNameForRole(role, email);
  }

  private normalizeEmailKey(email: string): string {
    return email.trim().toLowerCase();
  }

  private rememberDisplayNameForEmail(email: string, displayName?: string): void {
    if (!displayName) {
      return;
    }

    const trimmed = displayName.trim();
    if (!trimmed) {
      return;
    }

    const emailKey = this.normalizeEmailKey(email);
    if (!emailKey) {
      return;
    }

    this.displayNameByEmail = {
      ...this.displayNameByEmail,
      [emailKey]: trimmed,
    };
    this.persistDisplayNames();
  }

  private getDisplayNameForEmail(email: string): string | null {
    const emailKey = this.normalizeEmailKey(email);
    if (!emailKey) {
      return null;
    }
    return this.displayNameByEmail[emailKey] ?? null;
  }

  private restoreDisplayNames(): DisplayNameByEmail {
    if (typeof localStorage === 'undefined') {
      return {};
    }

    const raw = localStorage.getItem(this.displayNameStorageKey);
    if (!raw) {
      return {};
    }

    try {
      const parsed = JSON.parse(raw) as DisplayNameByEmail;
      if (!parsed || typeof parsed !== 'object') {
        return {};
      }
      return parsed;
    } catch {
      return {};
    }
  }

  private persistDisplayNames(): void {
    if (typeof localStorage === 'undefined') {
      return;
    }

    localStorage.setItem(this.displayNameStorageKey, JSON.stringify(this.displayNameByEmail));
  }

  private avatarForEmail(email: string): string {
    const seed = encodeURIComponent(email.toLowerCase());
    return `https://api.dicebear.com/9.x/notionists/svg?seed=${seed}`;
  }

  private extractErrorMessage(error: unknown, fallback: string): string {
    const candidate = error as {
      error?: {
        error?: {
          message?: string;
        };
        detail?: unknown;
      };
      message?: string;
    };

    const apiMessage = candidate.error?.error?.message;
    if (apiMessage) {
      return apiMessage;
    }

    const detail = candidate.error?.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail.trim();
    }
    if (Array.isArray(detail)) {
      for (const item of detail) {
        const msg = (item as {msg?: unknown})?.msg;
        if (typeof msg === 'string' && msg.trim()) {
          return msg.trim();
        }
      }
    }

    if (candidate.message) {
      return candidate.message;
    }
    return fallback;
  }
}
