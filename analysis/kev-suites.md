| Split | n | Jev acc. [95% CI] | Luna acc. [95% CI] | Jev − Luna [95% CI] | Kev-4B acc. (published) |
|---|---:|---|---|---|---:|
| transfer-v4-dev | 656 | 0.855 [0.826, 0.883] | 0.881 [0.856, 0.906] | -0.026 [-0.050, -0.002] | 0.817 |
| transfer-v4-test | 656 | 0.877 [0.849, 0.901] | 0.898 [0.876, 0.920] | -0.021 [-0.042, 0.000] | 0.838 |
| decision-v7-dev | 1264 | 0.845 [0.822, 0.865] | 0.862 [0.839, 0.883] | -0.017 [-0.032, -0.001] | 0.873 |
| decision-v7-test | 1200 | 0.835 [0.813, 0.856] | 0.846 [0.823, 0.869] | -0.011 [-0.029, 0.008] | 0.865 |

| Split | Jev ECE | Jev Brier | Jev confident errors | Kev-4B ECE raw / calibrated | Kev-4B Brier raw / calibrated |
|---|---:|---:|---:|---|---|
| transfer-v4-dev | 0.049 | 0.211 | 0.037 | – / 0.042 | – / 0.243 |
| transfer-v4-test | 0.035 | 0.177 | 0.024 | 0.085 / 0.017 | 0.242 / 0.224 |
| decision-v7-dev | 0.062 | 0.237 | 0.053 | – / 0.013 | – / 0.182 |
| decision-v7-test | 0.056 | 0.246 | 0.041 | 0.080 / 0.019 | 0.210 / 0.186 |

transfer-v4-test accuracy by source:

| Source | n | Jev | Luna |
|---|---:|---:|---:|
| composition_final_combination | 32 | 1.000 | 0.938 |
| composition_final_exception | 32 | 1.000 | 1.000 |
| composition_final_negation | 32 | 0.906 | 1.000 |
| contrastive_authorization | 40 | 1.000 | 1.000 |
| contrastive_deadline | 40 | 0.900 | 0.975 |
| emotion | 80 | 0.662 | 0.637 |
| mmlu | 80 | 0.863 | 0.925 |
| paws | 80 | 0.875 | 0.912 |
| qnli | 80 | 0.912 | 0.938 |
| sciq | 80 | 1.000 | 1.000 |
| tweet_offensive | 80 | 0.762 | 0.787 |

decision-v7-test accuracy by source:

| Source | n | Jev | Luna |
|---|---:|---:|---:|
| agnews | 80 | 0.850 | 0.812 |
| agnews_yn | 160 | 0.844 | 0.900 |
| amazon | 80 | 0.637 | 0.562 |
| banking77 | 80 | 0.738 | 0.800 |
| boolq | 80 | 0.912 | 0.912 |
| contrastive_age_eligibility | 40 | 1.000 | 1.000 |
| contrastive_quantity_limit | 40 | 1.000 | 1.000 |
| contrastive_return_window | 40 | 0.600 | 0.850 |
| contrastive_spend_threshold | 40 | 1.000 | 1.000 |
| dbpedia14 | 80 | 0.988 | 0.975 |
| imdb | 80 | 0.988 | 0.988 |
| mnli | 80 | 0.912 | 0.887 |
| sst5 | 80 | 0.637 | 0.650 |
| trec | 80 | 0.912 | 0.863 |
| yelp | 80 | 0.588 | 0.600 |
| yelp_yn | 80 | 0.875 | 0.912 |

