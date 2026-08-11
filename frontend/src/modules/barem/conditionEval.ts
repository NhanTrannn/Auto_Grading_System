/**
 * A browser-side stand-in for pipeline.py's `safe_eval_condition`, used only to
 * preview which conditional branch a value would land in.
 *
 * Deliberately a hand-written parser rather than `eval`/`new Function`: the
 * expressions come from a text field, and the Python side is an AST whitelist
 * precisely so barem text can never execute. Sharing that property keeps the
 * preview from being a weaker link than the thing it previews.
 *
 * Supports what the whitelist supports: numbers, strings, `value`, list
 * literals, unary `-`/`not`, `+ - * / %`, chained comparisons, `in`/`not in`,
 * `and`/`or`, and `.isdigit()`. Like the Python side, a `value` that is a
 * pure-digit string is converted to a number first (Python's `%` on `str` is
 * string formatting, not modulo).
 *
 * An approximation in one respect: JavaScript's `%` keeps the sign of the
 * dividend where Python's follows the divisor, so a negative `value` can
 * preview differently than it grades. Exam indices are positive, so this has no
 * practical effect here.
 */

type Value = number | string | boolean | Value[];

/**
 * A malformed expression, as opposed to a well-formed one that a particular
 * value happens to blow up (`"" % 4`). Only the former is worth reporting as a
 * barem defect — the latter is normal and means "this branch did not match".
 */
export class ConditionSyntaxError extends Error {}

interface Token {
  kind: "num" | "str" | "name" | "op";
  text: string;
}

const OPERATORS = [
  "==", "!=", "<=", ">=", "<", ">", "+", "-", "*", "/", "%", "(", ")", "[", "]", ",", ".",
];

function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;

  while (i < source.length) {
    const char = source[i];

    if (/\s/.test(char)) {
      i += 1;
      continue;
    }

    if (/[0-9]/.test(char)) {
      let text = "";
      while (i < source.length && /[0-9.]/.test(source[i])) text += source[i++];
      tokens.push({ kind: "num", text });
      continue;
    }

    if (char === '"' || char === "'") {
      const quote = char;
      let text = "";
      i += 1;
      while (i < source.length && source[i] !== quote) text += source[i++];
      if (i >= source.length) throw new ConditionSyntaxError("Thiếu dấu nháy đóng");
      i += 1;
      tokens.push({ kind: "str", text });
      continue;
    }

    if (/[A-Za-z_]/.test(char)) {
      let text = "";
      while (i < source.length && /[A-Za-z0-9_]/.test(source[i])) text += source[i++];
      tokens.push({ kind: "name", text });
      continue;
    }

    const twoChar = source.slice(i, i + 2);
    if (OPERATORS.includes(twoChar)) {
      tokens.push({ kind: "op", text: twoChar });
      i += 2;
      continue;
    }
    if (OPERATORS.includes(char)) {
      tokens.push({ kind: "op", text: char });
      i += 1;
      continue;
    }

    throw new ConditionSyntaxError(`Ký tự không hỗ trợ: '${char}'`);
  }

  return tokens;
}

const COMPARISONS = ["==", "!=", "<", "<=", ">", ">="];

function truthy(value: Value): boolean {
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "string") return value !== "";
  if (typeof value === "number") return value !== 0;
  return value;
}

/**
 * Refuse arithmetic and ordering on anything but a number, the way Python does.
 *
 * This is the whole point of the preview for blank or noisy values: `value` is
 * left as a string unless it is all digits, and Python then raises on
 * `"" % 4` (that is string formatting, not modulo) or `"abc" < 10`. The caller
 * treats the raise as "this branch did not match". Coercing instead — which
 * JavaScript is happy to do, turning `"" % 4` into 0 — would show a blank
 * answer confidently landing in branch 1.
 */
function numeric(value: Value, operator: string): number {
  if (typeof value !== "number") {
    throw new Error(`Không thể dùng '${operator}' với giá trị không phải số: ${JSON.stringify(value)}`);
  }
  return value;
}

function sameValue(left: Value, right: Value): boolean {
  if (Array.isArray(left) || Array.isArray(right)) return JSON.stringify(left) === JSON.stringify(right);
  return left === right;
}

class Parser {
  private pos = 0;

  constructor(
    private readonly tokens: Token[],
    private readonly scope: Record<string, Value>,
  ) {}

  parse(): Value {
    const result = this.parseOr();
    if (this.pos < this.tokens.length) throw new ConditionSyntaxError(`Thừa '${this.tokens[this.pos].text}'`);
    return result;
  }

  private peek(): Token | undefined {
    return this.tokens[this.pos];
  }

  private eat(text: string): boolean {
    const token = this.peek();
    if (token && token.text === text) {
      this.pos += 1;
      return true;
    }
    return false;
  }

  private expect(text: string): void {
    if (!this.eat(text)) throw new ConditionSyntaxError(`Thiếu '${text}'`);
  }

  // Both sides are parsed before combining, never inline as
  // `truthy(left) && truthy(this.parseAnd())`. JavaScript's `&&`/`||`
  // short-circuit, so a false left operand would skip the call that *consumes*
  // the right operand's tokens, and the leftovers surface as a bogus syntax
  // error on exactly the values that make the left side false.
  private parseOr(): Value {
    let left = this.parseAnd();
    while (this.eat("or")) {
      const right = this.parseAnd();
      left = truthy(left) || truthy(right);
    }
    return left;
  }

  private parseAnd(): Value {
    let left = this.parseNot();
    while (this.eat("and")) {
      const right = this.parseNot();
      left = truthy(left) && truthy(right);
    }
    return left;
  }

  private parseNot(): Value {
    if (this.eat("not")) return !truthy(this.parseNot());
    return this.parseComparison();
  }

  /** Python chains these: `1 < value < 10` is `1 < value and value < 10`. */
  private parseComparison(): Value {
    let left = this.parseSum();
    let result = true;
    let chained = false;

    for (;;) {
      const token = this.peek();
      if (!token) break;

      let operator: string | null = null;
      if (token.kind === "op" && COMPARISONS.includes(token.text)) {
        operator = token.text;
        this.pos += 1;
      } else if (token.kind === "name" && token.text === "in") {
        operator = "in";
        this.pos += 1;
      } else if (token.kind === "name" && token.text === "not" && this.tokens[this.pos + 1]?.text === "in") {
        operator = "not in";
        this.pos += 2;
      } else {
        break;
      }

      const right = this.parseSum();
      chained = true;
      result = result && this.compare(left, operator, right);
      left = right;
    }

    return chained ? result : left;
  }

  private compare(left: Value, operator: string, right: Value): boolean {
    if (operator === "in" || operator === "not in") {
      const list = Array.isArray(right) ? right : [];
      if (!Array.isArray(right) && typeof right === "string" && typeof left === "string") {
        const found = right.includes(left);
        return operator === "in" ? found : !found;
      }
      const found = list.some((item) => sameValue(item, left));
      return operator === "in" ? found : !found;
    }

    // `==`/`!=` accept anything and just answer false across types, exactly as
    // Python does.
    if (operator === "==") return sameValue(left, right);
    if (operator === "!=") return !sameValue(left, right);

    const a = numeric(left, operator);
    const b = numeric(right, operator);
    if (operator === "<") return a < b;
    if (operator === "<=") return a <= b;
    if (operator === ">") return a > b;
    return a >= b;
  }

  private parseSum(): Value {
    let left = this.parseTerm();
    for (;;) {
      if (this.eat("+")) left = numeric(left, "+") + numeric(this.parseTerm(), "+");
      else if (this.eat("-")) left = numeric(left, "-") - numeric(this.parseTerm(), "-");
      else return left;
    }
  }

  private parseTerm(): Value {
    let left = this.parseUnary();
    for (;;) {
      if (this.eat("*")) left = numeric(left, "*") * numeric(this.parseUnary(), "*");
      else if (this.eat("/")) left = numeric(left, "/") / numeric(this.parseUnary(), "/");
      else if (this.eat("%")) {
        const right = numeric(this.parseUnary(), "%");
        if (right === 0) throw new Error("Chia cho 0");
        left = numeric(left, "%") % right;
      } else return left;
    }
  }

  private parseUnary(): Value {
    if (this.eat("-")) return -numeric(this.parseUnary(), "-");
    return this.parsePostfix();
  }

  private parsePostfix(): Value {
    let value = this.parsePrimary();
    while (this.eat(".")) {
      const method = this.peek();
      if (!method || method.kind !== "name") throw new ConditionSyntaxError("Thiếu tên phương thức sau '.'");
      this.pos += 1;
      this.expect("(");
      this.expect(")");
      if (method.text !== "isdigit") throw new ConditionSyntaxError(`Chỉ hỗ trợ .isdigit(), không hỗ trợ .${method.text}()`);
      // Raises on a non-string, like Python. Worth knowing: `value.isdigit()`
      // can never return true, because a digit-only `value` has already been
      // converted to a number by then and raises here, while a non-digit one
      // answers false. Its real use is guarding a *different* string.
      if (typeof value !== "string") {
        throw new Error(".isdigit() chỉ dùng được với chuỗi");
      }
      value = value.length > 0 && /^[0-9]+$/.test(value);
    }
    return value;
  }

  private parsePrimary(): Value {
    const token = this.peek();
    if (!token) throw new ConditionSyntaxError("Biểu thức bị cắt ngang");

    if (token.kind === "num") {
      this.pos += 1;
      return Number(token.text);
    }
    if (token.kind === "str") {
      this.pos += 1;
      return token.text;
    }
    if (token.text === "(") {
      this.pos += 1;
      const inner = this.parseOr();
      this.expect(")");
      return inner;
    }
    if (token.text === "[") {
      this.pos += 1;
      const items: Value[] = [];
      if (!this.eat("]")) {
        do {
          items.push(this.parseOr());
        } while (this.eat(","));
        this.expect("]");
      }
      return items;
    }
    if (token.kind === "name") {
      this.pos += 1;
      if (token.text === "True") return true;
      if (token.text === "False") return false;
      if (token.text in this.scope) return this.scope[token.text];
      throw new ConditionSyntaxError(`Biến không xác định: '${token.text}'`);
    }

    throw new ConditionSyntaxError(`Không hiểu '${token.text}'`);
  }
}

export interface ConditionResult {
  matched: boolean;
  error?: string;
}

/**
 * Report a malformed expression, ignoring value-dependent runtime failures.
 *
 * Probed with a plain number so a well-formed arithmetic condition evaluates
 * cleanly; anything that still throws a ConditionSyntaxError is broken for
 * every student, not just some.
 */
export function conditionSyntaxError(expression: string): string | null {
  try {
    new Parser(tokenize(expression), { value: 1 }).parse();
    return null;
  } catch (error) {
    return error instanceof ConditionSyntaxError ? error.message : null;
  }
}

/** Mirrors safe_eval_condition's digit-string coercion before evaluating. */
export function evaluateCondition(expression: string, rawValue: string): ConditionResult {
  if (!expression.trim()) return { matched: false, error: "Điều kiện rỗng" };

  const value: Value = /^[0-9]+$/.test(rawValue) ? Number(rawValue) : rawValue;
  try {
    return { matched: truthy(new Parser(tokenize(expression), { value }).parse()) };
  } catch (error) {
    return { matched: false, error: (error as Error).message };
  }
}
