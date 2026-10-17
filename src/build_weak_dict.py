"""Build weak radical dictionary from PADT training data.

Learns mappings from surface forms to roots for weak radical cases where
CALIMA returns '#' but gold annotation exists.
"""
import sys
sys.path.insert(0, 'src')

from camel_tools.disambig.mle import MLEDisambiguator
from paths import PADT_TRAIN, PADT_TEST
import re
import json
from collections import defaultdict

def build_weak_radical_dict():
    """Build dictionary of weak radical forms -> roots from PADT train."""
    mle = MLEDisambiguator.pretrained('calima-msa-r13')
    
    # Dictionary: form -> (root_translit, root_arabic)
    weak_dict = {}
    stats = defaultdict(int)
    
    with open(PADT_TRAIN, encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.strip().split('\t')
            if len(parts) < 10:
                continue
            
            form = parts[1]
            upos = parts[3]
            misc = parts[9]
            
            # Get CALIMA analysis
            results = mle.disambiguate([form])
            if not results or not results[0].analyses:
                stats['no_analysis'] += 1
                continue
            
            analysis = results[0].analyses[0].analysis
            calima_root = analysis.get('root', '')
            
            # Only process weak radicals (those with '#')
            if '#' not in calima_root:
                stats['no_weak'] += 1
                continue
            
            stats['has_weak'] += 1
            
            # Extract gold root from MISC field
            root_match = re.search(r'Root=([^|]+)', misc)
            if not root_match:
                stats['no_gold_root'] += 1
                continue
            
            gold_root = root_match.group(1).strip()
            
            # Skip OOV
            if gold_root == 'OOV':
                stats['oov'] += 1
                continue
            
            # Convert PADT transliteration to Arabic
            from reconcile import padt_to_arabic
            arabic_root = padt_to_arabic(gold_root)
            
            if not arabic_root:
                stats['unmappable'] += 1
                continue

            # AN ENTRY THE RENDERER CANNOT USE IS NOISE. The digit-slot mechanism needs
            # 3 or 4 radicals, so a 1-2 or 5+ letter "root" — memorised loanword strings
            # like ليبيرال (7) or ءاميريك (7), plus 54 malformed 1-2 letter entries —
            # can never render. Measured on the 5,497-entry dictionary: only 5,357 were
            # 3-4 radicals, so this gate removes 140 entries that inflate the count and
            # supply a root the renderer must then reject for arity.
            if len(arabic_root) not in (3, 4):
                stats['wrong_arity'] += 1
                continue

            # Store the mapping
            if form not in weak_dict:
                weak_dict[form] = {
                    'root_translit': gold_root,
                    'root_arabic': arabic_root,
                    'calima_root': calima_root
                }
                stats['added'] += 1
    
    return weak_dict, dict(stats)

def test_weak_dict(weak_dict):
    """Test the weak dictionary on PADT test set."""
    mle = MLEDisambiguator.pretrained('calima-msa-r13')
    
    stats = defaultdict(int)
    
    with open(PADT_TEST, encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.strip().split('\t')
            if len(parts) < 10:
                continue
            
            form = parts[1]
            
            results = mle.disambiguate([form])
            if not results or not results[0].analyses:
                continue
            
            calima_root = results[0].analyses[0].analysis.get('root', '')
            
            if '#' not in calima_root:
                continue
            
            stats['weak_in_test'] += 1
            
            if form in weak_dict:
                stats['found_in_dict'] += 1
            else:
                stats['not_found'] += 1
    
    return dict(stats)

if __name__ == '__main__':
    print("Building weak radical dictionary from PADT train...")
    weak_dict, build_stats = build_weak_radical_dict()
    
    print(f"\nBuild statistics:")
    for k, v in sorted(build_stats.items()):
        print(f"  {k:<20} {v:>6}")
    
    print(f"\nDictionary size: {len(weak_dict)} forms")
    
    # Test on test set
    print("\nTesting on PADT test set...")
    test_stats = test_weak_dict(weak_dict)
    
    print(f"\nTest statistics:")
    for k, v in sorted(test_stats.items()):
        print(f"  {k:<20} {v:>6}")
    
    if test_stats['weak_in_test'] > 0:
        coverage = 100 * test_stats['found_in_dict'] / test_stats['weak_in_test']
        print(f"\nWeak radical coverage: {coverage:.1f}%")
    
    # Save to file
    output_path = 'data/weak_radical_dict.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(weak_dict, f, ensure_ascii=False, indent=2)
    
    print(f"\nSaved to {output_path}")
    
    # Show sample entries
    print("\nSample entries:")
    for i, (form, info) in enumerate(list(weak_dict.items())[:10]):
        print(f"  {form:<20} -> {info['root_arabic']:<10} ({info['root_translit']})")
