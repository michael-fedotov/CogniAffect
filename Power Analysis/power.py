from statsmodels.stats.power import TTestIndPower

params = {
          'effect_size': 0.5, 'alpha': 0.05, 
          'power': 0.80, 'ratio': 1.0,
          'alternative': 'two-sided'
         }

sample_size = TTestIndPower().solve_power(
                                **params
                                )
print(f"Required sample size (number of transcripts) based on the power analysis:  {round(sample_size)}")