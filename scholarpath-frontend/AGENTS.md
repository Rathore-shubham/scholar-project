<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## ScholarPath architecture
- Use TanStack file routes with a shared root application shell; preserve the framework’s navigation and SSR integration.
- Keep all scholarship fixtures and explicit eligibility rules in the frontend feature data module; no sample opportunity is a verified scheme.
- Isolate versioned localStorage persistence in the ScholarProvider, hydrate after mount, and validate restored data with Zod so a future API adapter can replace it safely.
- Keep profile forms, scholarship displays and page views in dedicated feature modules; use design-system Button controls and global semantic visual tokens.
- This prototype has no server submissions; future API integration must repeat client input schema validation on the server.
