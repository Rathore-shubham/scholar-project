# Scholarpath Magic

# Build a Clean and Minimal Student Scholarship Platform — ScholarPath AI

## 1. Project Overview

Build a modern, clean, minimal, and fully responsive student-facing web application called **ScholarPath AI**.

ScholarPath AI is an AI-powered scholarship discovery and eligibility platform that helps students find relevant scholarships, check their eligibility, understand eligibility requirements, track application deadlines, and access official application links.

The primary users are Indian students looking for government, private, NGO, and corporate CSR scholarships.

The UI should feel like a simple, trustworthy education platform. Prioritize usability, readability, clear information, and a straightforward student experience.

**Important design rule:** Keep the interface clean and minimal. Do not add fancy animations, parallax effects, animated backgrounds, excessive shadows, glassmorphism, excessive gradients, or unnecessary decorative elements.

## 2. Technology Stack

Use the following frontend technologies:

- React
- TypeScript
- Tailwind CSS
- Lucide React icons
- React Router for navigation
- Reusable components
- Responsive layouts for desktop, tablet, and mobile

Use Lucide icons only. Do not use emojis as interface icons.

For now, focus on building the frontend UI with realistic mock data. Keep the code organized so it can later connect to a FastAPI backend and PostgreSQL database with pgvector.

Do not implement a separate admin dashboard in this version.

## 3. Design System

### Overall theme

Use a light theme with a white background, subtle gray surfaces, dark text, and one restrained blue accent color.

Suggested colors:

- Primary background: `#FFFFFF`
- Secondary background: `#F8FAFC`
- Primary text: `#0F172A`
- Secondary text: `#64748B`
- Primary blue: `#2563EB`
- Borders: `#E2E8F0`
- Success: `#15803D`
- Warning: `#B45309`
- Error: `#B91C1C`

### UI styling

- Use a consistent 8px spacing system.
- Use subtle 1px borders.
- Use rounded corners between 8px and 12px.
- Use clean typography such as Inter.
- Use clear font sizes and readable line heights.
- Use minimal shadows only when necessary.
- Use generous whitespace.
- Use simple, flat buttons.
- Use consistent form fields and labels.
- Use small, restrained status badges.
- Keep content aligned to a consistent maximum-width container.

Avoid oversized headings, huge hero sections, colorful backgrounds, excessive card layouts, and unnecessary visual decoration.

### Animation rules

Do not use Framer Motion or other animation libraries.

Do not use scroll animations, animated counters, animated page transitions, floating elements, bouncing icons, or parallax effects.

Use only simple hover and focus states. Transitions should be subtle and brief, preferably under 150ms. Respect reduced-motion preferences.

## 4. Application Layout

Create a consistent application layout with a sidebar on desktop and a compact navigation menu on mobile.

### Sidebar

At the top, display the ScholarPath AI logo using a simple graduation-cap icon and the product name.

Navigation items:

1. Dashboard
2. Find Scholarships
3. My Applications
4. Saved Scholarships
5. My Profile

Use a light background, simple icons, and a clear active navigation indicator.

At the bottom, show:

- Help and Support
- Student profile avatar
- Student name
- Settings or account menu

Do not make the sidebar visually heavy.

### Top header

Include:

- Current page title
- Simple breadcrumb where useful
- Search shortcut where appropriate
- Notification bell
- Student avatar

Avoid adding unnecessary navigation elements.

## 5. Dashboard Page

Create a clean student dashboard that gives students an immediate overview of their scholarship opportunities.

### Welcome section

Display:

"Welcome back, Rahul"

Subtitle:

"Find scholarships that match your education and eligibility."

Add one primary button:

"Find Scholarships"

### Summary section

Show four compact summary cards:

1. Matching Scholarships
2. Eligible Scholarships
3. Saved Scholarships
4. Upcoming Deadlines

Use realistic example numbers and simple Lucide icons. Keep these cards small, aligned, and visually consistent.

### Recommended Scholarships

Display a section titled "Recommended for You".

Each scholarship item should contain:

- Scholarship name
- Provider name
- Education level
- Scholarship amount
- Application deadline
- Eligibility status
- Short eligibility explanation
- Save icon button
- View Details button

Example scholarship:

Name: National Merit Scholarship Example

Provider: Government Scholarship

Amount: Up to ₹25,000

Eligibility: Eligible

Reason: Your academic percentage and education level match the available criteria.

These are illustrative mock records. Do not represent them as verified real scholarship schemes.

### Upcoming Deadlines

Display a compact list of upcoming application deadlines, including scholarship name, deadline, and a button to view details.

### Empty and incomplete states

If the student's profile is incomplete, show a simple message:

"Complete your profile to discover scholarships that match your eligibility."

Include a button labeled "Complete Profile".

Do not overwhelm the dashboard with too many sections.

## 6. Find Scholarships Page

Create a scholarship discovery page with search, filters, sorting, and scholarship results.

### Page heading

Title: "Find Scholarships"

Description: "Discover scholarship opportunities based on your education, eligibility, and preferences."

### Search bar

Include a prominent but compact search field with placeholder:

"Search scholarships by name, provider, course, or keyword..."

### Filters

Add a clean filter panel containing:

- Education Level
- State
- Scholarship Provider
- Minimum Academic Percentage
- Family Income Range
- Scholarship Amount
- Gender, when applicable to the scheme
- Application Status

Include Clear Filters and Apply Filters actions.

On mobile, place filters inside a simple drawer or collapsible section.

### Scholarship results

Show the total result count and sorting options.

Available sorting options:

- Recommended
- Deadline: Earliest First
- Scholarship Amount: Highest First
- Recently Verified

Use a clean list or grid of scholarship cards. Prefer a two-column grid on suitable desktop screens and a single-column layout on mobile.

Each card must display:

- Scholarship name
- Provider
- Short description
- Amount or funding details
- Education level
- Deadline
- Eligibility status
- Save button
- View Details button

Provide pagination or a simple Load More button.

Do not use endless scrolling.

## 7. Scholarship Details Page

Create a dedicated page for each scholarship.

### Header

Display:

- Scholarship name
- Provider
- Scholarship amount
- Application deadline
- Eligibility status
- Save Scholarship button
- Apply on Official Website button

The external application button must clearly indicate that the user is leaving ScholarPath AI.

### Information sections

Use clean sections with clear headings:

1. Overview
2. Eligibility Criteria
3. Benefits and Scholarship Amount
4. Required Documents
5. Application Process
6. Important Dates
7. Official Source

### Eligibility Criteria

Display each eligibility requirement as a separate row.

Examples:

- Education level
- Minimum marks
- Annual family income
- State or domicile
- Institution or course requirements
- Other scheme-specific conditions

For each criterion, show one of these states:

- Meets requirement
- Does not meet requirement
- Information missing
- Unable to verify

Use restrained colors and text labels so status is understandable without relying on color alone.

Show the official source URL and last verification date.

Do not invent scholarship rules or present mock data as verified information.

## 8. Eligibility Checker Page

Build a clear eligibility checker that compares a student's profile with a scholarship's rules.

### Student information form

Include fields for:

- Full name
- Date of birth
- State of residence
- Education level
- Current course
- Institution
- Academic percentage or CGPA
- Annual family income
- Applicable category, when relevant
- Gender, when relevant to scholarship criteria

Use appropriate select fields, number inputs, date inputs, and radio buttons.

Mark required fields clearly. Make optional fields explicit.

Do not request Aadhaar numbers, bank account details, or other unnecessary sensitive information.

### Form actions

Provide:

- Check Eligibility
- Save Profile
- Reset Form

Validate user input and show clear inline error messages.

### Eligibility result

Display one of three main results:

**Eligible**

Show that all evaluated mandatory criteria are satisfied, with a list of the criteria that passed.

**Not Eligible**

Show which confirmed mandatory criteria were not satisfied and explain the reasons in plain language.

**Can't Tell Yet**

Show which information is missing or which criteria could not be verified. Allow the student to complete the missing information.

Below the result, show:

- Criteria-by-criteria breakdown
- Student's value
- Required value
- Result for each criterion
- Explanation
- Official source reference

Important: The eligibility result must not be calculated by an arbitrary AI-generated score. Use a rule-based eligibility result from the backend when integrated. Until then, use clearly labeled mock results for UI demonstration.

Never show a definitive eligible result if mandatory information is missing.

## 9. My Applications Page

Create a simple application tracking page.

Display a table on desktop and stacked application items on mobile.

Columns or fields:

- Scholarship Name
- Application Deadline
- Application Status
- Last Updated
- Actions

Example statuses:

- Interested
- Preparing Documents
- Ready to Apply
- Applied
- Awarded
- Not Selected

Allow users to update their local application status.

Include empty states when no scholarships have been saved or tracked.

Clearly distinguish statuses maintained by the student from statuses verified by an external scholarship provider.

## 10. Saved Scholarships Page

Create a page showing scholarships saved by the student.

Each item should show:

- Scholarship name
- Amount
- Deadline
- Eligibility status
- Remove from Saved action
- View Details action

Include filters for eligibility and deadline.

If the student has not saved any scholarships, display:

"You haven't saved any scholarships yet."

Add a button labeled "Explore Scholarships".

## 11. My Profile Page

Create a student profile page divided into simple sections:

1. Personal Information
2. Education Details
3. Family Income
4. Eligibility Information
5. Preferences

Display a profile completion indicator using a simple progress bar.

Allow students to edit and save their details.

Show a short privacy note explaining that profile information is used to match scholarships and check eligibility.

Avoid unnecessary personal information fields.

## 12. Notifications

Create a minimal notification panel for:

- Upcoming application deadlines
- Saved scholarship updates
- Profile completion reminders

Use sample notifications for the frontend prototype.

Do not claim that real email, SMS, or WhatsApp notifications have been sent.

## 13. Functional Requirements

Build the following frontend interactions:

- Navigation between all pages
- Search scholarships by keyword
- Filter and sort mock scholarship records
- Save and unsave scholarships
- Open scholarship details
- Fill out and validate the student profile form
- Display eligibility results using explicit mock rules
- Update application statuses
- Show empty states and error messages
- Display responsive mobile navigation
- Use confirmation dialogs for destructive actions when necessary

Use React state and reusable components. Keep the sample scholarship data in a separate mock data file.

Persist prototype data using localStorage only where appropriate, so saved scholarships and application status updates survive a page refresh. Keep this storage isolated so it can later be replaced with backend API calls.

Do not build fake backend functionality. Clearly separate mock data and simulated interactions from real backend integrations.

## 14. Reusable Components

Create reusable components for:

- Sidebar
- Header
- Search bar
- Scholarship card
- Eligibility badge
- Deadline indicator
- Filter panel
- Form fields
- Status badge
- Empty state
- Loading state
- Error state
- Confirmation dialog
- Notification panel

Use consistent naming and organize components into sensible folders.

## 15. Responsive Design

The application must work properly on:

- Desktop
- Laptop
- Tablet
- Mobile

On desktop, use a sidebar and spacious main content area.

On mobile, use a compact menu and single-column content. Ensure buttons and inputs are easy to tap, text does not overflow, and tables adapt to smaller screens.

## 16. Accessibility

- Use semantic HTML.
- Add accessible labels to inputs and buttons.
- Maintain adequate text contrast.
- Make navigation keyboard-accessible.
- Display text labels alongside eligibility status colors.
- Provide clear validation feedback.
- Use visible focus indicators.
- Respect reduced-motion settings.

## 17. Final Design Expectations

The finished product should resemble a clean, professional education SaaS dashboard.

The UI should prioritize the following:

1. Clear scholarship information
2. Simple eligibility checking
3. Easy scholarship discovery
4. Minimal visual clutter
5. Consistent typography and spacing
6. Trustworthy source information
7. Excellent usability on mobile

Do not add unnecessary charts, gamification, decorative illustrations, AI robot mascots, animated backgrounds, excessive cards, gradients, or complex effects.

Use subtle borders, simple icons, restrained colors, readable text, and consistent spacing.

Build a cohesive application with working navigation and functional mock interactions, not just a static landing page.

**Primary objective:** Make it easy for an Indian student to discover a scholarship, understand whether they qualify and why, and proceed to the official application page without confusion.

This project was built with [Lovable](https://lovable.dev).

**Live app**: https://scholarpath-magic.lovable.app

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/c3e5d653-f5fb-455e-947d-6047f1cb414f).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
