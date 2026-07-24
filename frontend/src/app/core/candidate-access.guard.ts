import {inject} from '@angular/core';
import {Router, type CanActivateFn} from '@angular/router';

import {resolveCandidateInvitationToken} from './candidate-access.util';

export const candidateAccessGuard: CanActivateFn = (route) => {
  const router = inject(Router);

  const inviteParam = route.queryParamMap.get('invite');
  const sessionParam = route.queryParamMap.get('session');
  const invitationToken = resolveCandidateInvitationToken({
    inviteParam,
    sessionParam,
  });

  if (invitationToken) {
    return true;
  }

  if (typeof localStorage !== 'undefined') {
    const persistedToken = localStorage.getItem('talentos.candidate.invitationToken');
    if (persistedToken?.trim()) {
      return true;
    }
  }

  return router.createUrlTree(['/auth/login']);
};
