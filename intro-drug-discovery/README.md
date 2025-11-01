# SMILES Transformer for De Novo Drug Discovery

## Overview

This educational notebook demonstrates how to build a transformer-based generative model for creating novel drug-like molecules using SMILES (Simplified Molecular Input Line Entry System) notation.

## What's Included

### 1. Complete Data Pipeline
- Automatic download of MOSES dataset (molecular generation benchmark)
- Fallback to curated drug molecules if download fails
- SMILES validation and filtering
- Drug-likeness criteria (Lipinski's Rule of Five)

### 2. Exploratory Analysis
- Molecular property distributions
- SMILES tokenization analysis
- Visualization with RDKit (2D molecular structures)
- Token frequency analysis

### 3. Model Architecture
- **Positional Encoding**: Sine/cosine functions for sequence position
- **Multi-Head Self-Attention**: Parallel attention mechanisms
- **Feed-Forward Networks**: Position-wise transformations
- **Causal Masking**: Autoregressive generation

### 4. Training
- Next-token prediction objective
- Learning rate scheduling with warmup
- Gradient clipping for stability
- Validation monitoring

### 5. Generation & Evaluation
- Multiple sampling strategies:
  - Greedy decoding
  - Temperature sampling
  - Top-k sampling
  - Top-p (nucleus) sampling
- Evaluation metrics:
  - Validity (chemical validity)
  - Uniqueness (distinct molecules)
  - Novelty (not in training set)
  - Drug-likeness (QED score)

## Requirements

```bash
pip install torch rdkit pandas numpy matplotlib seaborn scikit-learn tqdm requests
```

## Usage

1. Open `smiles_transformer_generation.ipynb`
2. Run all cells sequentially
3. The notebook will:
   - Download/generate training data
   - Train a transformer model
   - Generate novel molecules
   - Evaluate and visualize results

## Key Concepts

### SMILES Notation
```
CC(C)Cc1ccc(cc1)C(C)C(O)=O  # Ibuprofen
CN1C=NC2=C1C(=O)N(C(=O)N2C)C  # Caffeine
```

### Transformer for Molecules
- Treats molecules as sequences
- Learns grammar and constraints
- Generates valid structures
- Captures long-range dependencies

### Applications
- Lead optimization
- Scaffold hopping
- Library expansion
- Property-driven design

## Expected Results

After training (20 epochs, ~30 min on CPU):
- **Validity**: 85-95% chemically valid molecules
- **Uniqueness**: 70-90% unique structures
- **Novelty**: 60-80% not in training set
- **Drug-likeness**: QED ~0.5-0.7 (similar to training data)

## Learning Outcomes

Students will understand:
1. Molecular representations in ML
2. Transformer architecture for sequences
3. Autoregressive generation
4. Sampling strategies and their trade-offs
5. Evaluation metrics for generative models
6. RDKit for cheminformatics

## Next Steps

- **Conditional Generation**: Add property constraints
- **Reinforcement Learning**: Optimize specific properties
- **Larger Scale**: Train on full ChEMBL/ZINC databases
- **3D Generation**: Extend to conformer generation
- **Multi-objective**: Optimize multiple properties simultaneously

## References

- Vaswani et al. (2017): "Attention Is All You Need"
- Polykovskiy et al. (2020): "Molecular Sets (MOSES): A Benchmarking Platform"
- Segler et al. (2018): "Generating Focused Molecule Libraries for Drug Discovery"

## License

MIT License - Educational purposes

## Contact

For questions or improvements, please open an issue or submit a pull request.

