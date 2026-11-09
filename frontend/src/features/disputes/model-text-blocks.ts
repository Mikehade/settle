/**
 * The mediator's text as blocks: paragraphs (their lines kept apart) and "- " lists.
 */
export type Block = { kind: "paragraph"; lines: string[] } | { kind: "list"; items: string[] };

const BULLET = /^\s*[-*•]\s+/;

export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  // Blank lines separate blocks; within one, lines run on as a paragraph or a list.
  for (const chunk of text.trim().split(/\n\s*\n/)) {
    let current: Block | null = null;
    for (const raw of chunk.split("\n")) {
      const line = raw.trim();
      if (!line) continue;
      if (BULLET.test(line)) {
        const item = line.replace(BULLET, "");
        if (current?.kind === "list") current.items.push(item);
        else blocks.push((current = { kind: "list", items: [item] }));
      } else if (current?.kind === "paragraph") {
        current.lines.push(line);
      } else {
        blocks.push((current = { kind: "paragraph", lines: [line] }));
      }
    }
  }
  return blocks;
}
