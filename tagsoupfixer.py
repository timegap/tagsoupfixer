#! /usr/bin/env python3
# -*- coding: utf-8 -*-

'''

A Python tool to deal with dirty, bad and ugly HTML/XML snippets.

Timegap, june-october 2010

'''

import re
import sys
from collections import OrderedDict

# Quoted string regexp pattern generator
_patStr = lambda x: x + r'(?:[^' + x + r'\\]|\\.)*' + x
# General pattern for tags tokenization
_patTag = r'(<|</)([^>\s/]+)((?:[^>/"\']+|' + _patStr("'") + '|' + _patStr('"') + ')*)(/>|>)'
_patTagSep = '\u001f'
# Compile regexp for tags
R = re.compile
if sys.version_info[0] == 2: R = lambda p,f=0: re.compile(p,f|re.U)
_reTag = R(_patTag, re.M)
_reTagSep = R(_patTagSep+r'(?<!\\'+_patTagSep+')', re.M)
_reSepWithoutSpace = R('(\w)'+_patTagSep+'+(\w)')
#_reSepWithSpace = R('(\W)'+_patTagSep+'(\W)')

def strip_tags(inp, sep=' '):
    """
    Strip any tag in the input string and returns the result.

    >>> strip_tags('Hello <b>foo</b> <i>bar</i>.')
    'Hello foo bar.'

    >>> strip_tags('<span class="yo">thing</span><div>thang</div>')
    'thing thang'

    >>> strip_tags('blah bli blu<br />foo bar wiz<br />')
    'blah bli blu foo bar wiz'

    >>> strip_tags('<br />blah bli blu<br />foo bar wiz')
    'blah bli blu foo bar wiz'
    """
    # TODO: clean this buggy mess...
    # We must leave spaces in place of tags u know
    # Escape separator
    #inp = _reTagSep.sub('\\'+_patTagSep, inp)
    # Replace tags by separator
    inp = _reTag.sub(_patTagSep, inp)
    # Make sure we have at least one space between words
    inp = _reSepWithoutSpace.sub(r'\1'+sep+r'\2', inp)
    #inp = _reSepWithSpace.sub(r'\1\2', inp)
    # Strip separators
    inp = _reTagSep.sub('', inp)
    # Return result
    return inp

def fix_tags(input, removeEmptyTags = False, changeTagsNameCase = 0,
             unNestTags = None, check = False, verbose = False):
    """
    Returns tidy HTML from dirty input. Fixes overlapping tags, can change
    tags name case, remove empty tags and "unnest" tags. Doesn't automatically
    close tags, lacks a mechanism to correctly handle unclosed EmptyElementTags
    (as <br>). BRs are currently rewritten as XHTML BRs (<br/>).
    By "unest" I mean rewrite code in order to "flatten" the tree of tags.
    For example: <foo bar="wiz" a="1"><foo wiz="bar" a="2">blah</foo></foo> with
    unNestTags = ['foo'] and removeEmptyTags to True will output
    <foo wiz="bar" a="1" bar="wiz">blah</foo>

    removeEmptyTags: remove matching StartTag/EndTag with no content/blanks
    changeTagsNameCase: > 0 => uppercase, < 0 => lowercase, 0 => no change
    unNestTags: list of tag names to "unest"
    check: compare stripped input with stripped output and print some excuse
           if these don't match, even if verbose is False
    verbose: not quiet

    StartTag        -> <tagname[...]>
    EndTag          -> </tagname[...]>
    EmptyElementTag -> <tagname[...]/>

    Loosely similar to TagSoup:
    http://home.ccil.org/~cowan/XML/tagsoup/

    And BeautifulSoup:
    http://codespeak.net/lxml/elementsoup.html

    To check XML well-formedness:
    http://www.w3schools.com/Dom/dom_validate.asp

    TODO: correctly handle unclosed EmptyElementTags (as <br>)
    TODO: proper error handling
    TODO: stream-based implementation...

    >>> fix_tags('<span fontWeight="bold">It is a <span fontStyle="italic">silly</span> test.</span>', unNestTags=['span'])
    '<span fontWeight="bold">It is a </span><span fontWeight="bold" fontStyle="italic">silly</span><span fontWeight="bold"> test.</span>'

    >>> fix_tags('<span fontWeight="bold"><span fontStyle="italic"><span styleName="small">blahblahblah</span></span> blah </span>', unNestTags=['span'], removeEmptyTags=True)
    '<span fontWeight="bold" fontStyle="italic" styleName="small">blahblahblah</span><span fontWeight="bold"> blah </span>'
    """

    if verbose:
        def assume(cond, msg):
            if not cond: print('tagsoupfixer: Parser bug:', msg)
    else:
        def assume(cond, msg): pass

    # Tags name comparator
    if changeTagsNameCase == 0: tagNameEqual = lambda a, b: a.lower() == b.lower()
    else: tagNameEqual = lambda a, b: a == b
    # Normalize tags to unNest
    if unNestTags:
        if changeTagsNameCase > 0: unNestTags = map(str.upper, unNestTags)
        else: unNestTags = map(str.lower, unNestTags)
        unNestTags = set(unNestTags)

    # Tokenize input
    tokens = _reTag.split(input)

    # Debugging
    #~ f = open('pat.txt', mode='w'); f.write(_patTag); f.close()
    #~ print(str(tokens).encode('cp1252'))

    # Initialize parser state
    # -- text output
    output = ''
    # -- tags stack; format: [(name, textBefore, markup)*]
    #               example: [('div', '... blah <b>di dum</b> ...', '<div class="main">'), ...]
    stack = []
    TAG_NAME = 0; TEXT_BEFORE = 1; MARKUP = 2; ATTRIBUTES = 3
    # -- contextual boolean states
    markupComplete = inTag = endTag = emptyElementTag = False
    # -- buffers for tag name and attributes
    curTagName = curTagAttributes = ''

    # http://www.w3.org/TR/2008/REC-xml-20081126/#sec-starttags
    for tok in tokens:

        # Simplistic XML parser (don't parse attributes)
        # Open StartTag / EmptyElementTag
        if tok == '<':
            assume(not inTag, 'Unexpected "<" inside markup.')
            inTag = True
        # Open EndTag
        elif tok == '</':
            assume(not inTag, 'Unexpected "</" inside markup.')
            inTag = endTag = True
        # Close StartTag / EndTag
        elif tok == '>':
            assume(inTag, 'Unexpected ">" outside markup.')
            markupComplete = True
        # Close EmptyElementTag
        elif tok == '/>':
            assume(inTag, 'Unexpected "/>" outside markup.')
            markupComplete = emptyElementTag = True
        # Continue *Tag
        elif inTag:
            # Tag name
            if not curTagName:
                if changeTagsNameCase > 0: curTagName = tok.upper()
                elif changeTagsNameCase < 0: curTagName = tok.lower()
                else: curTagName = tok
            # Tag attributes
            else: curTagAttributes = tok
        # Text
        else:
            output += tok

        # We parsed a complete tag (StartTag, EndTag or EmptyElementTag)
        if markupComplete:
            # Quick'n'dirty hack to deal with BRs
            if tagNameEqual(curTagName, 'br'):
                emptyElementTag = True
            # Produce current tag
            curTag = "<{}{}{}{}>".format(
                '/' if endTag else '',
                curTagName,
                curTagAttributes,
                '/' if emptyElementTag else ''
            )
            # Process current tag
            # -- EmptyElementTag
            if emptyElementTag:
                # No text to process, output the markup
                output += curTag
            # -- StartTag
            elif not endTag:
                # Push current tag on the stack with current output as textBefore
                # and reset output.
                if unNestTags and curTagName in unNestTags:
                    attrs = parse_attributes(curTagAttributes)
                    # 20/01/2011: we HAVE to merge the parent's attributes if any
                    if len(stack) and stack[-1][TAG_NAME] == curTagName and stack[-1][ATTRIBUTES] and attrs:
                        tmp = stack[-1][ATTRIBUTES].copy()
                        tmp.update(attrs)
                        attrs = tmp
                    tag = [curTagName, output, curTag, attrs]
                else: tag = [curTagName, output, curTag]
                output = ''
                stack.append(tag)
            # -- EndTag, try to match a StartTag
            else:
                if len(stack) == 0:
                    # Drop this tag
                    if verbose: print('tagsoupfixer: '+curTag+': End tag with no match, tag dropped.')
                elif tagNameEqual(stack[-1][TAG_NAME], curTagName):
                    # Unnest of the poor (with the parent)
                    if unNestTags and len(stack) > 1 and curTagName in unNestTags and stack[-2][TAG_NAME] == curTagName:
                        attrs = stack[-1][ATTRIBUTES]
                        # 20/01/2011: already done at StartTag
                        #attrs.update(stack[-2][ATTRIBUTES])
                        attrs = build_attributes(attrs)
                        stack[-1][MARKUP] = '</' + curTagName + '>' + '<' + curTagName + attrs + '>'
                        #if verbose: print('tagsoupfixer: '+curTag+': rewrote parent: '+stack[-1][MARKUP])
                        curTag += stack[-2][MARKUP]
                    # Properly nested tags
                    if not removeEmptyTags or len(output.strip()) > 0:
                        # Tag is not empty / We don't have to strip empty tags
                        output = stack[-1][TEXT_BEFORE] + stack[-1][MARKUP] + output + curTag
                    else:
                        # Tag is empty and we have to strip its nasty markup
                        output = stack[-1][TEXT_BEFORE] + output
                        if verbose: print('tagsoupfixer: '+curTag+': Removed empty tag.')
                    stack.pop()
                elif len(stack) > 1:
                    # Detect improperly nested tags
                    overlap = None
                    for i in reversed(range(len(stack)-1)):
                        # Overlapping tags !!
                        if tagNameEqual(stack[i][TAG_NAME], curTagName):
                            overlap = i; break
                    if overlap is not None:
                        if verbose:
                            print('tagsoupfixer: ['+curTagName+','+stack[overlap-1][TAG_NAME]+']: Overlapping tags.')
                        # Fix overlapping by properly closing the tag
                        tag = stack[overlap]
                        for i in range(overlap+1, len(stack)):
                            stack[i][MARKUP] = '</'+tag[TAG_NAME]+'>'+stack[i][MARKUP]+tag[MARKUP]
                        output += curTag
                        stack[overlap+1][TEXT_BEFORE] = tag[TEXT_BEFORE] + tag[MARKUP] + stack[overlap+1][TEXT_BEFORE]
                        stack.pop(overlap)
            # Reset tag parser state
            markupComplete = inTag = endTag = emptyElementTag = False
            curTagName = curTagAttributes = ''

    # Output remaining elements on the stack
    for i in reversed(range(len(stack))):
        output = stack[i][TEXT_BEFORE] + stack[i][MARKUP] + output

    # Cludgy hack to fix empty tags when unnesting
    if unNestTags and removeEmptyTags:
        output = fix_tags(output, removeEmptyTags=True)

    if check:
        oh = strip_tags(input)
        my = strip_tags(output)
        if oh != my:
            print('tagsoupfixer: Sorry, I stripped out some text, aaaaaaargh.\n', oh, '\n', my)

    return output

def escape(s, chars=None):
    if not chars: chars = ''
    chars += '\\'
    for c in chars:
        s = s.replace(c, '\\'+c)
    return s

def unescape(s, chars=None):
    if not chars: chars = ''
    chars += '\\'
    for c in chars:
        s = s.replace('\\'+c, c)
    return s

_patNameChar = '[^>\s/"\']'
_reAttr = re.compile('\s*('+_patNameChar+'+)\s*=\s*('+_patNameChar+'+|'+_patStr('"')+'|'+_patStr("'")+')')

def parse_attributes(attributes):
    # Input text
    attributes = attributes.strip()
    if not attributes: return None
    # Iterates over parsed keys/values
    attrs = OrderedDict()
    for m in _reAttr.finditer(attributes):
        key, value = m.group(1), m.group(2)
        quotes = '"\''
        if value[0] in quotes:
            value = unescape(value[1:-1], quotes)
        attrs[key] = value
    return attrs or None

def build_attributes(attrs):
    buf = ''
    for key in attrs:
        q = '"'; value = q + escape(attrs[key], q) + q
        buf += ' ' + key + '=' + value
    return buf

if __name__ == "__main__":
    import doctest
    print("--- tagsoupfixer\n")
    doctest.testmod()
    test = """
</nomatch><emptytag thing="a" />
<span><big><big><big> b </span> c </big></big></big>
This is <B>bold, <I>bold italic, </b>italic, </i>normal text</I>
<p machin="<truc>">Cuivre champleve, emaille, <i></i>dore.</p><br>
<p><strong>emaux : </strong>couleurs inconnues.</p><br>
<p><strong>Historique :</strong> coll. du vicomte de Janze en 1866 ; Vte Janze, 16 avril 1866, Paris, Drouot, n° 73. Localisation actuelle inconnue.</p><br>
Description d'apres le catalogue de vente :<br>
<p><em>Plaque <strong>carree</em>, provenant</strong> sans doute d'une chasse, et representant le sujet de la Creche. Sur le premier plan, la Vierge est couchee sur un lit de parade. a droite, dans le haut, se trouve la figure de saint Joseph assis.</p><br>
<p><strong>Bibliographie :</strong> inedit.</p><br>"""
    print('Source:', test, '\n')
    print('Result:', fix_tags(test, removeEmptyTags=True, check=True, verbose=True))
