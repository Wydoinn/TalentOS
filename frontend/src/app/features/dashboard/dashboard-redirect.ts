import { Component, OnInit, inject } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-dashboard-redirect',
  standalone: true,
  template: `
    <div class="min-h-[40vh] flex items-center justify-center text-sm text-gray-500">
      Loading dashboard...
    </div>
  `,
})
export class DashboardRedirectComponent implements OnInit {
  private authService = inject(AuthService);
  private router = inject(Router);

  ngOnInit(): void {
    const role = this.authService.currentUser()?.role;
    let target = '/auth/login';

    if (role === 'pm') {
      target = '/dashboard/manager';
    } else if (role === 'candidate') {
      target = '/exam';
    }

    void this.router.navigateByUrl(target, {replaceUrl: true});
  }
}
