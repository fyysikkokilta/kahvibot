$(function () {
	//Mostly copied from http://www.highcharts.com/stock/demo/lazy-loading

    // convert an object into an array, used for handling data
    function objToArray(o) { return Object.keys(o).map(function(k) {return [parseInt(k), o[k]];}) }

    function afterSetExtremes(e) {

        //var chart = $('#container').highcharts();
		    var chart = Highcharts.charts[0]; // ??? - vs. above


        chart.showLoading('Fetching data...');

        url = Config.url;

        $.getJSON(url, {s: e.min, e: e.max}, function(data) {

          data = objToArray(data);

		      //TODO: multiple series
          chart.series[0].setData(data);
        
        });

        chart.hideLoading();

    }


 	//TODO: see https://github.com/highcharts/highcharts/blob/master/samples/data/from-sql.php on how to set up the queries for averaged data. most importantly:
	//TODO: also check out how meso does this and consider that as well
	/*
		// find the right table
		// two days range loads minute data
		if ($range < 2 * 24 * 3600 * 1000) {
			$table = 'stockquotes';
			
		// one month range loads hourly data
		} elseif ($range < 31 * 24 * 3600 * 1000) {
			$table = 'stockquotes_hour';
			
		// one year range loads daily data
		} elseif ($range < 15 * 31 * 24 * 3600 * 1000) {
			$table = 'stockquotes_day';
		// greater range loads monthly data
		} else {
			$table = 'stockquotes_month';
		} 
	 */

    // url from original example
    // url = "https://www.highcharts.com/samples/data/from-sql.php?callback=?"

    // get url from config file
    url = Config.url;


    end = new Date().getTime()

    $.getJSON(url, {s: 0, e: end}, function (data) {


        data = objToArray(data);

        //data = [].concat(data, [[Date.UTC(2014, 9, 14, 19, 59), null]]);

        // Create the chart

        //$('#container').highcharts('StockChart', {

        Highcharts.StockChart('container', {

            title: {
                text: 'Kahvin määrä kiltiksellä ajan funktiona'
            },

            chart: {
                zoomType: 'x'
            },

            navigator: {
                adaptToUpdatedData: false,
                series: {
                    data: data
                }
            },

            scrollbar: {
                liveRedraw: false
            },

            rangeSelector: {
                buttons: [{
                    type: 'hour',
                    count: 1,
                    text: '1h'
                }, {
                    type: 'day',
                    count: 1,
                    text: '1d'
                },
				//TODO: week (?)
				{
                    type: 'month',
                    count: 1,
                    text: '1m'
                },
				//TODO: remove year?
				{
                    type: 'year',
                    count: 1,
                    text: '1y'
                }, {
                    type: 'all',
                    text: 'All'
                }],
                inputEnabled: false, // it supports only days
                selected: 4 // all
            },

            xAxis: {
                events: {
                    afterSetExtremes: afterSetExtremes
                },
				minRange: 60 * 1000 // one minute (TODO: increase? 10 minutes?)
            },

            yAxis: {
                floor: 0
            },

            series: [{
                name: 'kahvi',
                data: data,
                tooltip: {
                    valueDecimals: 2
                },
                dataGrouping: {
                    enabled: false
                }
            }]
        });
    }); //NOTE

});

