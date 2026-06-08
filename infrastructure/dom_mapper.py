from typing import List, Dict, Any
from core.exceptions import FormSolvingError
from utils.logger import get_logger
import re
import difflib

logger = get_logger("DOMMapper")

class JobstreetDOMMapper:
    def __init__(self, page):
        self.page = page
        
    def _t(self, sel):
        return ' '.join(sel.xpath('.//text()').getall()).strip() if sel else ''

    async def extract_questions(self) -> List[Dict[str, Any]]:
        """Extract application questions from the current form page using Scrapling for extreme speed."""
        from scrapling import Selector
        
        try:
            await self.page.wait_for_selector(
                "fieldset, select, textarea, input:not([type='hidden'])",
                state="attached", timeout=5000
            )
            await self.page.wait_for_timeout(1000)
        except Exception:
            pass
            
        html = await self.page.content()
        parsed = Selector(html)
        groups = []

        # 1. Individual Inputs
        inputs = parsed.css("select, textarea, input:not([type='hidden']):not([type='radio']):not([type='checkbox']):not([type='file'])")
        for inp in inputs:
            try:
                target_id = inp.attrib.get("id")
                if not target_id: continue
                
                label_els = parsed.css(f"label[for='{target_id}']")
                if not label_els: continue
                label_el = label_els[0]
                
                strong = label_el.css("strong, span")
                q_text = self._t(strong[0]) if strong else self._t(label_el)
                q_text = re.sub(r"\*", "", q_text).strip()
                if not q_text or len(q_text) < 4: continue
                
                style = inp.attrib.get("style", "").lower()
                if "display: none" in style or "visibility: hidden" in style: continue
                
                is_required = "*" in self._t(label_el)
                tag = inp.element.tag.lower()
                q_type = "Text"
                options = []
                
                if tag == "select":
                    q_type = "Dropdown"
                    opts = inp.css("option")
                    for opt in opts:
                        val = self._t(opt)
                        opt_val = opt.attrib.get("value", "")
                        if val and "pilih" not in val.lower() and opt_val:
                            options.append(val)
                            
                groups.append({
                    "label": q_text,
                    "type": q_type,
                    "options": options,
                    "label_for": target_id,
                    "is_required": is_required
                })
            except Exception as e:
                logger.debug(f"Error parsing input: {e}")
                continue

        # 2. React-style radio groups (fieldset)
        fieldsets = parsed.css("fieldset[role='radiogroup']")
        for fs in fieldsets:
            try:
                legends = fs.css("legend")
                if not legends: continue
                q_text = re.sub(r"\*", "", self._t(legends[0])).strip()
                if not q_text or len(q_text) < 4: continue
                
                fs_id = fs.attrib.get("id", "")
                radios = fs.css("input[type='radio']")
                options = []
                for r in radios:
                    r_id = r.attrib.get("id")
                    if r_id:
                        lbls = fs.css(f"label[for='{r_id}']")
                        if lbls: options.append(self._t(lbls[0]))
                if options:
                    groups.append({
                        "label": q_text,
                        "type": "Choice",
                        "options": options,
                        "label_for": fs_id
                    })
            except Exception as e:
                logger.debug(f"Error parsing fieldset: {e}")
                continue

        # 3. Checkbox groups (fieldset without role)
        checkbox_groups = parsed.css("fieldset:not([role='radiogroup'])")
        for cg in checkbox_groups:
            try:
                inputs_el = cg.css("input[type='checkbox']")
                if not inputs_el: continue
                legends = cg.css("legend")
                if not legends: continue
                q_text = re.sub(r"\*", "", self._t(legends[0])).strip()
                if not q_text or len(q_text) < 4: continue
                
                cg_id = cg.attrib.get("id", "")
                options = []
                for c in inputs_el:
                    c_id = c.attrib.get("id")
                    if c_id:
                        lbls = cg.css(f"label[for='{c_id}']")
                        if lbls: options.append(self._t(lbls[0]))
                if options:
                    groups.append({
                        "label": q_text,
                        "type": "MultiChoice",
                        "options": options,
                        "label_for": cg_id
                    })
            except Exception as e:
                logger.debug(f"Error parsing checkbox group: {e}")
                continue

        # 4. Old-school checkboxes (with _A_ prefix)
        loose_checkboxes = parsed.css("input[type='checkbox'][id*='_A_']")
        processed_prefixes = set()
        for cb in loose_checkboxes:
            try:
                cb_id = cb.attrib.get("id", "")
                prefix = re.sub(r"_A_\d+$", "", cb_id)
                if not prefix or prefix in processed_prefixes: continue
                processed_prefixes.add(prefix)

                heading_text = ""
                heading_label = parsed.css(f"label[for='{prefix}']")
                if heading_label:
                    heading_text = self._t(heading_label[0])
                else:
                    # Parent element previous sibling extraction is harder in scrapling, fallback to prefix
                    heading_text = prefix
                
                group_inputs = parsed.css(f"input[id^='{prefix}_A_']")
                opts = []
                for gi in group_inputs:
                    gi_id = gi.attrib.get("id", "")
                    lbl = parsed.css(f"label[for='{gi_id}']")
                    if lbl: opts.append(self._t(lbl[0]))
                
                if opts:
                    groups.append({
                        "label": heading_text,
                        "type": "MultiChoice",
                        "options": opts,
                        "label_for": prefix
                    })
            except Exception as e:
                logger.debug(f"Error parsing loose checkbox: {e}")
                continue
                
        # Remove duplicates
        unique_groups = []
        seen = set()
        for g in groups:
            key = (g['label'], g['type'], tuple(g.get('options', [])))
            if key not in seen:
                seen.add(key)
                unique_groups.append(g)
                
        return unique_groups

    async def solve_question(self, question: Dict[str, Any], answer: str):
        page = self.page
        label_for = question.get("label_for")
        q_type = question["type"]
        label = question["label"]
        try:
            if q_type == "Dropdown":
                select = question.get("target_el") or await page.query_selector(f"#{label_for}")
                answer_parts = [a.strip() for a in answer.split('||')] if "||" in answer else [answer]
                if select:
                    options = await select.query_selector_all("option")
                    opt_texts = [await opt.inner_text() for opt in options]
                    opt_texts = [t.strip() for t in opt_texts]
                    
                    best_match_idx = -1
                    for ans in answer_parts:
                        ans_lower = ans.lower()
                        for idx, t in enumerate(opt_texts):
                            if t.lower() and (ans_lower in t.lower() or t.lower() in ans_lower):
                                best_match_idx = idx
                                break
                        if best_match_idx != -1: break
                        
                        valid_texts = [t.lower() for t in opt_texts if t.strip()]
                        matches = difflib.get_close_matches(ans_lower, valid_texts, n=1, cutoff=0.7)
                        if matches:
                            matched_lower = matches[0]
                            for idx, t in enumerate(opt_texts):
                                if t.lower() == matched_lower:
                                    best_match_idx = idx
                                    break
                        if best_match_idx != -1: break
                    
                    if best_match_idx != -1:
                        val = await options[best_match_idx].evaluate("el => el.value")
                        try: await select.select_option(value=val, timeout=3000, force=True)
                        except: pass
                        await select.evaluate(f"""(el) => {{
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')?.set;
                            if (setter) setter.call(el, '{val}');
                            else el.value = '{val}';
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}""")
                        return True
                    
                    try:
                        idx = int(answer.split('||')[0].strip()) - 1
                        opt_els = [o for o in options if await o.get_attribute("value")]
                        if 0 <= idx < len(opt_els):
                            val = await opt_els[idx].evaluate("el => el.value")
                            try: await select.select_option(value=val, timeout=3000, force=True)
                            except: pass
                            await select.evaluate(f"""(el) => {{
                                const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')?.set;
                                if (setter) setter.call(el, '{val}');
                                else el.value = '{val}';
                                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}""")
                            return True
                    except ValueError:
                        pass
                        
            elif q_type in ("Choice", "MultiChoice"):
                fieldset = await page.query_selector(f"fieldset#{label_for}")
                if fieldset:
                    group_inputs = await fieldset.query_selector_all("input[type='radio'], input[type='checkbox']")
                else:
                    prefix = label_for if "_A_" not in label_for else re.sub(r"_A_\d+$", "", label_for)
                    group_inputs = await page.query_selector_all(f"input[id^='{prefix}_A_'], input[id='{label_for}']")
                
                if q_type == "MultiChoice":
                    answer_parts = [a.strip().lower() for a in answer.split('|')]
                else:
                    answer_parts = [a.strip().lower() for a in answer.split('||')] if "||" in answer else [answer.lower()]
                
                clicked_any = False
                for gi in group_inputs:
                    gi_id = await gi.get_attribute("id") or ""
                    lbl_el = await page.query_selector(f"label[for='{gi_id}']")
                    if lbl_el:
                        lbl_text = (await lbl_el.inner_text()).strip()
                        for part in answer_parts:
                            if part and (part in lbl_text.lower() or lbl_text.lower() in part):
                                is_checked = await gi.is_checked()
                                if not is_checked:
                                    await lbl_el.click()
                                clicked_any = True
                                if q_type == "Choice":
                                    return True
                                break
                if clicked_any:
                    return True
            else:
                inp = question.get("target_el") or await page.query_selector(f"#{label_for}")
                if inp:
                    ans_to_fill = answer.split('||')[-1].strip() if "||" in answer else answer
                    await inp.fill(ans_to_fill)
                    return True
        except Exception as e:
            logger.error(f"Failed to solve question '{label}' with '{answer}': {e}")
            raise FormSolvingError(f"Could not interact with form element: {e}")
