import {inject} from '@angular/core';
import {Router, type CanActivateFn} from '@angular/router';

import {AuthService} from './auth.service';

export const pendingAuthGuard: CanActivateFn = (route) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (authService.isAuthenticated()) {
    const role = authService.currentUser()?.role;
    if (role === 'pm') {
      return router.createUrlTree(['/dashboard/manager']);
    }
    if (role === 'candidate') {
      return router.createUrlTree(['/exam']);
    }
    return router.createUrlTree(['/dashboard']);
  }

  const expectedStep = String(route.data['step'] ?? '');
  if (authService.hasPendingStep('register_face')) {
    return expectedStep === 'register_face'
      ? true
      : router.createUrlTree(['/auth/face-register']);
  }
  if (authService.hasPendingStep('verify_face')) {
    return expectedStep === 'verify_face'
      ? true
      : router.createUrlTree(['/auth/face-verify']);
  }

  return router.createUrlTree(['/auth/login']);
};
