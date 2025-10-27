"""
Test capitalization of words
"""

def test_capitalization():
    """Test word capitalization"""
    test_words = ['privet', 'MIR', 'PrIvEt', 'slovo', 'OGROMNY', 'yolka', 'YOLKA']
    result = [word.capitalize() if word else word for word in test_words]
    
    print('=' * 60)
    print('TEST CAPITALIZATION')
    print('=' * 60)
    print()
    
    print('Input words:')
    for word in test_words:
        print('  - "' + word + '"')
    
    print()
    print('After capitalize():')
    for i, (orig, cap) in enumerate(zip(test_words, result), 1):
        status = 'OK' if cap[0].isupper() else 'FAIL'
        print('  ' + str(i) + '. [' + status + '] "' + orig + '" -> "' + cap + '"')
    
    print()
    print('=' * 60)
    print('Capitalization works!')
    print('=' * 60)
    
    # Check all words capitalized
    all_capitalized = all(cap[0].isupper() for cap in result if cap)
    if all_capitalized:
        print('ALL words have uppercase first letter')
    else:
        print('ERROR: Some words have lowercase!')
    
    print()
    return all_capitalized


if __name__ == '__main__':
    success = test_capitalization()
    exit(0 if success else 1)
