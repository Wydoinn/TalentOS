import { inject } from '@angular/core';
import { Router, type CanActivateFn } from '@angular/router';
import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = (_route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (authService.isAuthenticated()) {
    return true;
  }

  if (authService.hasPendingStep('register_face')) {
    return router.createUrlTree(['/auth/face-register']);
  }

  if (authService.hasPendingStep('verify_face')) {
    return router.createUrlTree(['/auth/face-verify']);
  }

  const next = normalizeNextUrl(state.url);
  const candidateToken = typeof localStorage !== 'undefined'
    ? localStorage.getItem('talentos.candidate.invitationToken')?.trim()
    : null;
  if (candidateToken && (state.url.startsWith('/exam') || state.url.startsWith('/assessment'))) {
    return router.createUrlTree(['/auth/candidate/login'], {
      queryParams: next ? {next} : undefined,
    });
  }

  return router.createUrlTree(['/auth/login'], {
    queryParams: next ? {next} : undefined,
  });
};

function normalizeNextUrl(rawUrl: string | undefined): string | null {
  if (!rawUrl) {
    return null;
  }

  const trimmed = rawUrl.trim();
  if (!trimmed.startsWith('/')) {
    return null;
  }

  if (trimmed.startsWith('/auth/')) {
    return null;
  }

  return trimmed;
}
