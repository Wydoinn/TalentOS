import {Routes} from '@angular/router';
import { MainLayoutComponent } from './layout/main-layout';
import { authGuard } from './core/auth.guard';
import { candidateAccessGuard } from './core/candidate-access.guard';
import { pendingAuthGuard } from './core/pending-auth.guard';
import { roleGuard } from './core/role.guard';

export const routes: Routes = [
  {
    path: 'auth',
    children: [
      {
        path: 'login',
        loadComponent: () => import('./features/auth/login').then(m => m.LoginComponent)
      },
      {
        path: 'register',
        loadComponent: () => import('./features/auth/register').then(m => m.RegisterComponent)
      },
      {
        path: 'candidate/login',
        canActivate: [candidateAccessGuard],
        loadComponent: () => import('./features/auth/candidate-login').then(m => m.CandidateLoginComponent)
      },
      {
        path: 'candidate/register',
        redirectTo: 'candidate/login',
        pathMatch: 'full'
      },
      {
        path: 'candidate/access',
        loadComponent: () => import('./features/auth/candidate-access').then(m => m.CandidateAccessComponent)
      },
      {
        path: 'face-register',
        canActivate: [pendingAuthGuard],
        data: { step: 'register_face' },
        loadComponent: () => import('./features/auth/face-register').then(m => m.FaceRegisterComponent)
      },
      {
        path: 'face-verify',
        canActivate: [pendingAuthGuard],
        data: { step: 'verify_face' },
        loadComponent: () => import('./features/auth/face-verify').then(m => m.FaceVerifyComponent)
      },
      { path: '', redirectTo: 'login', pathMatch: 'full' }
    ]
  },
  {
    path: 'exam',
    canActivate: [authGuard, roleGuard],
    data: { roles: ['candidate'] },
    loadComponent: () => import('./features/exam/exam').then(m => m.ExamComponent)
  },
  {
    path: 'assessment',
    canActivate: [authGuard, roleGuard],
    data: { roles: ['candidate'] },
    loadComponent: () => import('./features/assessment/assessment-session').then(m => m.AssessmentSessionComponent)
  },
  {
    path: '',
    component: MainLayoutComponent,
    canActivate: [authGuard],
    children: [
      {
        path: 'dashboard/manager',
        canActivate: [roleGuard],
        data: { roles: ['pm'] },
        loadComponent: () => import('./features/dashboard/dashboard').then(m => m.DashboardComponent)
      },
      {
        path: 'dashboard',
        loadComponent: () => import('./features/dashboard/dashboard-redirect').then(m => m.DashboardRedirectComponent)
      },
      {
        path: 'candidates',
        canActivate: [roleGuard],
        data: { roles: ['pm'] },
        loadComponent: () => import('./features/candidates/candidate-list').then(m => m.CandidateListComponent)
      },
      {
        path: 'candidates/:id',
        canActivate: [roleGuard],
        data: { roles: ['pm'] },
        loadComponent: () => import('./features/candidates/candidate-profile').then(m => m.CandidateProfileComponent)
      },
      {
        path: 'jobs/create',
        canActivate: [roleGuard],
        data: { roles: ['pm'] },
        loadComponent: () => import('./features/jobs/job-create').then(m => m.JobCreateComponent)
      },
      {
        path: 'jobs/:id/candidates',
        canActivate: [roleGuard],
        data: { roles: ['pm'] },
        loadComponent: () => import('./features/jobs/job-candidates').then(m => m.JobCandidatesComponent)
      },
      {
        path: 'jobs',
        canActivate: [roleGuard],
        data: { roles: ['pm'] },
        loadComponent: () => import('./features/jobs/job-roles').then(m => m.JobRolesComponent)
      },
      {
        path: 'insights',
        canActivate: [roleGuard],
        data: { roles: ['pm'] },
        loadComponent: () => import('./features/insights/ai-insights').then(m => m.AiInsightsComponent)
      },
      {
        path: 'reports',
        canActivate: [roleGuard],
        data: { roles: ['pm'] },
        loadComponent: () => import('./features/reports/assessment-reports').then(m => m.AssessmentReportsComponent)
      },
      {
        path: 'chat',
        canActivate: [roleGuard],
        data: { roles: ['pm'] },
        loadComponent: () => import('./features/chat/chat').then(m => m.ChatComponent)
      },
      {
        path: 'settings',
        canActivate: [roleGuard],
        data: { roles: ['pm'] },
        loadComponent: () => import('./features/settings/settings').then(m => m.SettingsComponent)
      },
      { path: '', redirectTo: 'dashboard/manager', pathMatch: 'full' }
    ]
  },
  { path: '**', redirectTo: 'dashboard' }
];
