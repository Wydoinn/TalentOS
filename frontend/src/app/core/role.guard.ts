import {inject} from '@angular/core';
import {Router, type CanActivateFn} from '@angular/router';

import {AuthService, type UserRole} from './auth.service';

export const roleGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  const requiredRoles = (route.data['roles'] as UserRole[] | undefined) ?? [];

  if (!authService.isAuthenticated()) {
    const next = normalizeNextUrl(state.url);
    return router.createUrlTree(['/auth/login'], {
      queryParams: next ? {next} : undefined,
    });
  }

  if (requiredRoles.length === 0) {
    return true;
  }

  const role = authService.currentUser()?.role;
  if (role && requiredRoles.includes(role)) {
    return true;
  }

  if (role === 'pm') {
    return router.createUrlTree(['/dashboard/manager']);
  }
  if (role === 'candidate') {
    return router.createUrlTree(['/exam']);
  }

  return router.createUrlTree(['/dashboard']);
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
