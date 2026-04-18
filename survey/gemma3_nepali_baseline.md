# Gemma 3 4B — Nepali Baseline Report

**Model:** `mlx-community/gemma-3-4b-it-bf16`
**Date:** 2026-04-18 18:46:20
**Seed:** 42

## Summary

| Benchmark | n | Metric | Score |
|---|---|---|---|
| FLORES-200 en2ne | 100 | chrF++ | 38.15 |
| FLORES-200 en2ne | 100 | BLEU | 6.94 |
| FLORES-200 ne2en | 100 | chrF++ | 55.88 |
| FLORES-200 ne2en | 100 | BLEU | 28.79 |

## FLORES-200 en2ne

- **n:** 100
- **chrF_plus_plus:** 38.15
- **BLEU:** 6.94
- **errors:** 0
- **elapsed_sec:** 83.2

### Samples

```
{
  "src": "Crime, and ill-will toward foreigners in general, is virtually unknown in Greenland. Even in the towns, there are no \"rough areas.\"",
  "hyp": "ग्रीनलैंडमा अपराध, र विदेशीहरूमा सामान्यतया दुर्व्यवहार लगभग अज्ञात छ। यहाँसम्म पनि, शहरहरूमा पनि \"कठोर क्षेत्र\" छैनन्।",
  "ref": "अपराध र सामान्यतया विदेशीहरूप्रति खराब इच्छा, ग्रीनल्याण्डमा लगभग अज्ञात छ। शहरहरूमा पनि, त्यहाँ कुनै “असभ्य क्षेत्रहरू” छैनन्।"
}
```

```
{
  "src": "It is the biggest acquisition in eBay's history.",
  "hyp": "यसले एबेको इतिहासमै सबैभन्दा ठूलो अधिग्रहण हो।",
  "ref": "यो ई-बेको इतिहासमा सबैभन्दा ठूलो अधिग्रहण हो।"
}
```

```
{
  "src": "Ovechkin's first assist of the night was on the game-winning goal by rookie Nicklas Backstrom;",
  "hyp": "ओवेचकिनको रातिको पहिलो असिस्ट निकला खेल जिताउने गोलमा, रोकीले निकला निक्लास बेकस्ट्रमले।",
  "ref": "ओभेच्किन (Ovechkin) को रातको खेलको पहिलो सहयोग रुकी निकलास ब्याकस्ट्रोम (Nicklas Backstrom) को खेल जिताउने गोलमा थियो;"
}
```

```
{
  "src": "A hospitality exchange network is the organization that connects travelers with locals in the cities they are going to visit.",
  "hyp": "पर्यटन आदानप्रदान नेटवर्क भनेको यात्रीहरूलाई उनीहरू भ्रमण गर्ने शहरका स्थानीयहरूसँग जोड्ने स organisation्ठन हो।",
  "ref": "अतिथि सेवा आदानप्रदान सञ्जाल भनेको त्यो सङ्गठन हो जसले यात्रीलाई तिनीहरू घुम्न जान लागेका सहरहरूमा स्थानीयहरूसँग जोड्छन्।"
}
```

```
{
  "src": "In Berlin, police estimated 6,500 protestors.",
  "hyp": "बेर्लिनमा, प्रहरीले ६,५०० प्रदर्शनकारीहरूको अनुमान लगाउनु थियो।",
  "ref": "बर्लिनमा, पुलिसले 6,500 प्रदर्शनकारीहरू भएको अनुमान गरे।"
}
```

## FLORES-200 ne2en

- **n:** 100
- **chrF_plus_plus:** 55.88
- **BLEU:** 28.79
- **errors:** 0
- **elapsed_sec:** 65.2

### Samples

```
{
  "src": "अपराध र सामान्यतया विदेशीहरूप्रति खराब इच्छा, ग्रीनल्याण्डमा लगभग अज्ञात छ। शहरहरूमा पनि, त्यहाँ कुनै “असभ्य क्षेत्रहरू” छैनन्।",
  "hyp": "Crime and generally ill will towards foreigners are almost unknown in Greenland. Even in cities, there are no “uncivilized areas.”",
  "ref": "Crime, and ill-will toward foreigners in general, is virtually unknown in Greenland. Even in the towns, there are no \"rough areas.\""
}
```

```
{
  "src": "यो ई-बेको इतिहासमा सबैभन्दा ठूलो अधिग्रहण हो।",
  "hyp": "This is the largest acquisition in eBay’s history.",
  "ref": "It is the biggest acquisition in eBay's history."
}
```

```
{
  "src": "ओभेच्किन (Ovechkin) को रातको खेलको पहिलो सहयोग रुकी निकलास ब्याकस्ट्रोम (Nicklas Backstrom) को खेल जिताउने गोलमा थियो;",
  "hyp": "Nicklas Backstrom’s goal in the first assist of Ovechkin’s night was the deciding factor in the game.",
  "ref": "Ovechkin's first assist of the night was on the game-winning goal by rookie Nicklas Backstrom;"
}
```

```
{
  "src": "अतिथि सेवा आदानप्रदान सञ्जाल भनेको त्यो सङ्गठन हो जसले यात्रीलाई तिनीहरू घुम्न जान लागेका सहरहरूमा स्थानीयहरूसँग जोड्छन्।",
  "hyp": "A community-based tourism network is an organization that connects travelers with local people in the cities they are visiting.",
  "ref": "A hospitality exchange network is the organization that connects travelers with locals in the cities they are going to visit."
}
```

```
{
  "src": "बर्लिनमा, पुलिसले 6,500 प्रदर्शनकारीहरू भएको अनुमान गरे।",
  "hyp": "In Berlin, police estimated that there were 6,500 protesters.",
  "ref": "In Berlin, police estimated 6,500 protestors."
}
```
