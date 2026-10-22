# ScholarPath editorial redesign

## Goal
Apply the supplied editorial identity to the existing ScholarPath experience without rebuilding it or changing its features.

## Work
- Introduce semantic forest-green, ivory, paper, sage, terracotta, charcoal, and border tokens; load a refined serif for selected headings while retaining a readable sans-serif for controls and body text.
- Recompose the dashboard around a search-first editorial welcome, a concise match summary, scholarship opportunity rows, and a chronological deadline rail.
- Give discovery results a directory-like row treatment and refine the existing details, eligibility, profile, saved, application, and shared navigation surfaces with consistent typography, dividers, and restrained status accents.
- Preserve all existing routes, mock fixtures, forms, local storage, eligibility behavior, and interactions; do not add backend services or dependencies.

## Technical notes
- Keep the existing TanStack Start route architecture and feature modules.
- Use shared semantic CSS variables and existing design-system buttons; keep styles responsive and honor reduced motion.
- Verify the preview and available build/test signals after changes.
