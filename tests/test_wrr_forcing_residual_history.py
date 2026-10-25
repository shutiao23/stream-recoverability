import numpy as np
from sklearn.linear_model import Ridge
from stream_recoverability.experiments.tr_revision.ridge_history import YearExcludedRidge


def fixture():
    rng=np.random.default_rng(515)
    x=rng.normal(size=(800,4));years=np.repeat([2000,2001,2002,2003],200)
    y=12+x@np.array([2.,-.3,.7,.1])+rng.normal(0,.2,len(x))
    x[10:15,0]=np.nan;y[250:255]=np.nan
    return x,y,years


def test_two_year_statistics_match_independent_sklearn_fit():
    x,y,years=fixture();model=YearExcludedRidge(x,y,years)
    train=~np.isin(years,[2001,2003])&np.isfinite(x).all(axis=1)&np.isfinite(y)
    held=years==2003;reference=Ridge(alpha=1).fit(x[train],y[train])
    np.testing.assert_allclose(model.predict(held,[2001,2003]),reference.predict(x[held]),atol=1e-10)
    assert model.coefficients([2001,2003]) is model.coefficients([2003,2001])


def test_held_target_year_cannot_change_training_residuals():
    x,y,years=fixture();original=YearExcludedRidge(x,y,years)
    changed=y.copy();changed[years==2001]+=1000
    perturbed=YearExcludedRidge(x,changed,years)
    first=original.residual_history(2001,[2000,2001,2002,2003])
    second=perturbed.residual_history(2001,[2000,2001,2002,2003])
    assert np.isnan(first[years==2001]).all()
    np.testing.assert_allclose(first,second,atol=1e-9,equal_nan=True)


def test_insufficient_training_covariates_stay_unavailable():
    x=np.ones((200,3));y=np.arange(200,dtype=float);years=np.repeat([2000,2001],100)
    model=YearExcludedRidge(x,y,years,min_rows=120)
    assert np.isnan(model.predict(years==2001,[2001])).all()
