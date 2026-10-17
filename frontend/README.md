# SyncroFin — frontend

SPA em React 19 + TypeScript, construída com Vite e estilizada com Tailwind CSS 4 (componentes shadcn/ui).
A arquitetura completa está em [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) e o guia de desenvolvimento em
[`../docs/DEVELOPMENT.md`](../docs/DEVELOPMENT.md).

```bash
npm ci
npm run dev            # servidor de desenvolvimento (proxy /api -> backend)
npm run typecheck      # tsc nativo (TypeScript 7)
npm run lint           # eslint (inclui jsx-a11y)
npm test               # vitest
npm run i18n:check     # cobertura das traduções (en, pt-BR, es); --strict falha se divergirem
npm run build          # typecheck + build de produção em dist/
```

- Alias `@/` aponta para `src/`.
- Textos: `src/locales/*.json` (`en`, `pt-BR`, `es`); chave nova vai nos três.
- PWA: `public/manifest.webmanifest` e `public/sw.js` (o service worker nunca guarda `/api`).
- Em produção o nginx (`default.conf.template`) serve o build e faz proxy de `/api/` para o backend.
