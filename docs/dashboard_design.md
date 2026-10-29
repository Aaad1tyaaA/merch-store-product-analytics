# Dashboard design standards

I use this checklist to make the report readable and useful for a growth decision. It draws on published guidance; it is a practical review standard, not a claim that every dashboard needs the same layout.

## Before building

| Check | Application in this report |
|---|---|
| Identify the audience and decision | A Head of Growth needs to choose the next experiment. Each page answers a different part of that decision. |
| Fix metric definitions first | Sessions, transactions and cookies stay distinct. Conversion uses purchasing sessions; revenue uses valid deduplicated orders. |
| Establish trustworthy coverage | The funnel uses the reliable 61-day window. The Evidence page retains all 92 source days and explains the partial-day audit limitation. |
| Reconcile the numbers | SQL model checks, exported control totals, measure-expression checks and evidence comparisons run before presentation review. |
| Separate observation from causality | Revenue scenarios and sampling intervals have different labels. Promotion and activation associations are not presented as intervention effects. |

Microsoft recommends choosing the metrics and detail level for the audience's decisions, prioritising important information and removing unnecessary clutter. I apply those principles to these report pages, while keeping the distinction between a Power BI report and a service dashboard. [Microsoft: dashboard design](https://learn.microsoft.com/en-us/power-bi/create-reports/service-dashboards-design-tips).

## Typography and layout

- I use **Segoe UI** throughout, with four roles: **28 pt page/insight headings, 32 pt KPI values, 16 pt visual titles and 12 pt body/table/axis/data text**. Weight and spacing establish emphasis instead of switching font families.
- Table cells, captions, slicers and navigation labels have a 12 pt floor. Values and their explanatory labels use separate typographic emphasis.
- Pages open at **Fit to width** so increasing content height does not shrink all text to fit the entire page. The Customers page has taller panels for readable coefficient, retention and experiment tables. On a small screen, scrolling is preferable to shrinking the text further.
- I review the report at its intended viewing size, with the editing panes collapsed, and check for truncated labels, collisions, hidden values and internal scrollbars. Desktop editing panes consume space that would otherwise belong to the report.
- The same role uses the same size and colour on every page. Tables align comparable numbers, and page content follows a consistent grid.

Tableau emphasises a clear visual hierarchy, predictable interactions, context and design for the actual display. Microsoft's typography guidance recommends a screen-friendly sans-serif font, a restrained hierarchy, aligned numbers and consistent formatting. The specific 12 pt floor is my readability choice, supported by TDI's table/filter/label standard. [Tableau: visual best practices](https://help.tableau.com/current/blueprint/en-gb/bp_visual_best_practices.htm), [Microsoft: typography for data](https://github.com/microsoft/skills-for-fabric/blob/main/skills/powerbi-report-cli/references/design/typography.md), [TDI: data-visualisation style guide](https://www.tdi.texas.gov/styleguide/style-guide-for-data-visualization-tools.html).

## Charts and visible values

- Bars and columns show values directly, including session counts, currency amounts and percentages. Counts and USD use whole numbers; comparison percentages use one decimal where it helps.
- The purchase journey uses horizontal bars with a common zero baseline. Step order remains chronological; discovery comparisons are ranked by session volume.
- I use concise page aliases on axes while retaining the original observed page titles in the exported data.
- Dense daily trends use selective labels and a clearly dated latest-value summary. Printing 92 labels on each line would make them collide; exact observations remain available through **Show data** and the source CSV.
- Titles explain the comparison, and captions identify the unit, time window or important limitation. Labels and numbers carry meaning alongside colour.
- Unrelated regression terms and alternative test sizes do not get a grand total. Rates from different denominators are not added together.

## Accessibility and interaction checks

- Normal text colours meet a **4.5:1 contrast ratio**, checked automatically for the report's text/background combinations. Colour is not the only way to distinguish a series: legends, labels and values remain visible.
- Analytical visuals have descriptive alternative text. The tab order starts with navigation, then follows the content from top to bottom and left to right.
- The sidebar uses native page-navigation buttons with a current-page highlight. In Desktop, Ctrl+click follows the action; selecting a button and pressing Ctrl+Enter also works.
- Data-view alternatives remain available. An automated contrast/structure check is not a complete screen-reader audit.

These checks follow Microsoft's recommendations for consistent titles and labels, sufficient contrast, alternative text and keyboard navigation. [Microsoft: accessible Power BI reports](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports).
